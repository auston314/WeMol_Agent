from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount
import uvicorn
import json
import os
import random
import string
from rdkit import Chem
from rdkit.Chem import AllChem

# Create an MCP server for conformation generation
mcp = FastMCP("conformation_server")

def conformation_generation(input_molecules: str, num_conformers: int = 10, max_attempts: int = 1000) -> str:
    """
    Generate 3D conformations for molecules.
    
    Args:
        input_molecules: Can be:
            - A filename (with extension .sd, .sdf, or .smi)
            - A SMILES string
            - A JSON string containing a list of SMILES strings
        num_conformers: Number of conformers to generate per molecule
        max_attempts: Maximum attempts for conformer generation
    
    Returns:
        The output filename containing the generated conformations
    """
    mol_data_path = os.path.join(os.path.dirname(__file__), '..', 'mcp_client', 'mol_data')
    
    # Ensure the mol_data directory exists
    os.makedirs(mol_data_path, exist_ok=True)
    
    # Case 1: Check if input is a filename
    if input_molecules.endswith(('.sd', '.sdf', '.smi')):
        input_file = os.path.join(mol_data_path, input_molecules)
        
        if not os.path.exists(input_file):
            return f"Error: Input file {input_molecules} not found in mol_data directory"
        
        # Read molecules from file
        mols = []
        if input_molecules.endswith('.smi'):
            # Read SMILES file
            with open(input_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        parts = line.split()
                        smiles = parts[0]
                        mol = Chem.MolFromSmiles(smiles)
                        if mol:
                            # Add name if provided
                            if len(parts) > 1:
                                mol.SetProp("_Name", parts[1])
                            mols.append(mol)
        else:
            # Read SDF file
            suppl = Chem.SDMolSupplier(input_file, removeHs=False)
            mols = [mol for mol in suppl if mol is not None]
        
        # Generate output filename
        base_name = input_molecules.rsplit('.', 1)[0]
        output_filename = f"{base_name}Conf.sd"
        output_file = os.path.join(mol_data_path, output_filename)
        
    # Case 2: Input is SMILES string(s)
    else:
        # Try to parse as JSON list
        try:
            smiles_list = json.loads(input_molecules)
            if not isinstance(smiles_list, list):
                smiles_list = [input_molecules]
        except json.JSONDecodeError:
            # Single SMILES string
            smiles_list = [input_molecules]
        
        # Convert SMILES to molecules
        mols = []
        for smiles in smiles_list:
            mol = Chem.MolFromSmiles(smiles)
            if mol:
                mols.append(mol)
        
        # Generate random filename
        random_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        output_filename = f"{random_name}.sd"
        output_file = os.path.join(mol_data_path, output_filename)
    
    if not mols:
        return "Error: No valid molecules found in input"
    
    # Generate conformations for each molecule
    writer = Chem.SDWriter(output_file)
    
    for mol in mols:
        # Add hydrogens if not present
        mol = Chem.AddHs(mol)
        
        # Generate 3D conformations
        try:
            # Generate multiple conformers
            conf_ids = AllChem.EmbedMultipleConfs(
                mol, 
                numConfs=num_conformers,
                maxAttempts=max_attempts,
                randomSeed=42
            )
            
            if len(conf_ids) == 0:
                print(f"Warning: Could not generate conformers for molecule {mol.GetProp('_Name') if mol.HasProp('_Name') else 'unknown'}")
                continue
            
            # Optimize each conformer
            for conf_id in conf_ids:
                AllChem.MMFFOptimizeMolecule(mol, confId=conf_id)
            
            # Write all conformers to file
            for conf_id in conf_ids:
                writer.write(mol, confId=conf_id)
                
        except Exception as e:
            print(f"Error generating conformers for molecule: {str(e)}")
            continue
    
    writer.close()
    
    return output_filename

# Define our tools
@mcp.tool()
def generate_conformation(input_molecules: str) -> any:
    """Generate 3D conformations of input molecules. 
       The input molecules can be a list of SMILES strings or a file path of input molecules. 
       The input molecule file should contain molecules either in SMILES or in SDF format. 
       
       It returns a file name of the generated conformations of the molecules."""
    print("Input molecules = ", input_molecules)
    try:
        # Add robust error handling
        if not isinstance(input_molecules, str):
            return "No input molecules are provided"
        
        # Use the conformation_generation function
        output_file = conformation_generation(input_molecules)
        
        if output_file.startswith("Error"):
            print(f"Error in conformation generation: {output_file}")
            return output_file
        
        print(f"Conformations saved to file {output_file}")
        return f"Conformations have been generated and saved to file {output_file}"
        
    except Exception as e:
        # Return error message
        print(f"Error in conformation generation: {str(e)}")
        return f"Error in conformation service: {str(e)}"

# Add additional tools here
# ,,,,

# Mount the MCP SSE app at root
app = Starlette(routes=[
    Mount("/", app=mcp.sse_app()),
])

if __name__ == "__main__":
    # Listen on all interfaces, port 3003
    uvicorn.run(app, host="0.0.0.0", port=3003)
