from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount
import uvicorn
import json
import os
import random
import string
import time
from rdkit import Chem
from rdkit.Chem import rdDistGeom
from nvmolkit import mmffOptimization as mmff

# Create an MCP server for GPU-accelerated conformation generation
mcp = FastMCP("nvmolkit_conformation_server")

def nvmolkit_conformation_generation(input_molecules: str, num_conformers: int = 250, max_iters: int = 100) -> str:
    """
    Generate 3D conformations for molecules using Nvidia's nvMolKit for GPU-accelerated optimization.
    
    Args:
        input_molecules: Can be:
            - A filename (with extension .sd, .sdf, or .smi)
            - A SMILES string
            - A JSON string containing a list of SMILES strings
        num_conformers: Number of conformers to generate per molecule
        max_iters: Maximum iterations for MMFF optimization
    
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
        output_filename = f"{base_name}NvConf.sd"
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
        output_filename = f"{random_name}_nv.sd"
        output_file = os.path.join(mol_data_path, output_filename)
    
    if not mols:
        return "Error: No valid molecules found in input"
    
    # Process molecules for conformer generation
    processed_mols = []
    mol_names = []
    
    for mol in mols:
        # Store molecule name
        mol_name = mol.GetProp('_Name') if mol.HasProp('_Name') else f"mol_{len(processed_mols)}"
        mol_names.append(mol_name)
        
        # Add hydrogens
        mol = Chem.AddHs(mol)
        
        # Generate conformers using RDKit
        try:
            time_start = time.time()
            conf_ids = rdDistGeom.EmbedMultipleConfs(mol, numConfs=num_conformers)
            
            if len(conf_ids) == 0:
                print(f"Warning: Could not generate conformers for molecule {mol_name}")
                continue
            
            # Add hydrogens again (as per nvMolKit example)
            mol = Chem.AddHs(mol)
            
            processed_mols.append(mol)
            print(f"Generated {len(conf_ids)} conformers for {mol_name} in {time.time() - time_start:.2f}s")
            
        except Exception as e:
            print(f"Error generating conformers for molecule {mol_name}: {str(e)}")
            continue
    
    if not processed_mols:
        return "Error: Could not generate conformers for any molecules"
    
    # Optimize conformers using nvMolKit GPU acceleration
    try:
        print("Starting GPU-accelerated MMFF optimization with nvMolKit...")
        time_opt_start = time.time()
        
        energies = mmff.MMFFOptimizeMoleculesConfs(
            processed_mols,
            maxIters=max_iters,
        )
        
        opt_time = time.time() - time_opt_start
        print(f"GPU optimization completed in {opt_time:.2f}s")
        
        # Log energies for each molecule
        for i, (mol, energy_list) in enumerate(zip(processed_mols, energies)):
            print(f"Molecule {mol_names[i]}: {len(energy_list)} conformers optimized")
            print(f"  Energy range: {min(energy_list):.2f} - {max(energy_list):.2f} kcal/mol")
        
    except Exception as e:
        print(f"Error during nvMolKit optimization: {str(e)}")
        return f"Error: GPU optimization failed - {str(e)}"
    
    # Write optimized conformers to SDF file
    writer = Chem.SDWriter(output_file)
    
    for mol_idx, (mol, energy_list) in enumerate(zip(processed_mols, energies)):
        mol_name = mol_names[mol_idx]
        
        # Write each conformer with its energy
        for conf_id, energy in enumerate(energy_list):
            # Set properties
            mol.SetProp("_Name", mol_name)
            mol.SetProp("Energy", f"{energy:.4f}")
            mol.SetProp("ConformerID", str(conf_id))
            
            # Write conformer to file
            try:
                writer.write(mol, confId=conf_id)
            except Exception as e:
                print(f"Warning: Could not write conformer {conf_id} for {mol_name}: {str(e)}")
                continue
    
    writer.close()
    
    # Count total conformers written
    total_conformers = sum(len(e) for e in energies)
    print(f"Successfully wrote {total_conformers} conformers for {len(processed_mols)} molecules to {output_filename}")
    
    return output_filename


# Define our tools
@mcp.tool()
def generate_conformation_gpu(input_molecules: str, num_conformers: int = 250, max_iters: int = 100) -> str:
    """Generate 3D conformations of input molecules using GPU-accelerated nvMolKit. 
       
       The input molecules can be:
       - A list of SMILES strings (as JSON array)
       - A single SMILES string
       - A file path to molecules in SMILES (.smi) or SDF (.sd, .sdf) format
       
       The function generates conformers using RDKit and optimizes them using Nvidia's nvMolKit
       for GPU-accelerated MMFF optimization.
       
       Args:
           input_molecules: Input molecules (SMILES or filename)
           num_conformers: Number of conformers to generate per molecule (default: 250)
           max_iters: Maximum iterations for MMFF optimization (default: 100)
       
       Returns:
           A message with the output filename containing the generated conformations."""
    
    print(f"Input molecules = {input_molecules}")
    print(f"Conformers per molecule = {num_conformers}, Max iterations = {max_iters}")
    
    try:
        # Validate input
        if not isinstance(input_molecules, str):
            return "Error: No input molecules are provided"
        
        # Use the nvmolkit_conformation_generation function
        output_file = nvmolkit_conformation_generation(
            input_molecules, 
            num_conformers=num_conformers,
            max_iters=max_iters
        )
        
        if output_file.startswith("Error"):
            print(f"Error in conformation generation: {output_file}")
            return output_file
        
        print(f"GPU-optimized conformations saved to file {output_file}")
        return f"Conformations have been generated using GPU acceleration and saved to file {output_file}"
        
    except Exception as e:
        # Return error message
        error_msg = f"Error in GPU conformation service: {str(e)}"
        print(error_msg)
        return error_msg


@mcp.tool()
def get_server_info() -> dict:
    """Get information about the nvMolKit conformation server capabilities."""
    return {
        "server_name": "nvMolKit GPU Conformation Server",
        "description": "GPU-accelerated molecular conformation generation using Nvidia nvMolKit",
        "features": [
            "GPU-accelerated MMFF optimization",
            "Supports SMILES strings and SDF files",
            "Batch processing of multiple molecules",
            "Energy calculation for all conformers",
            "High-throughput conformer generation (default 250 per molecule)"
        ],
        "input_formats": [".smi", ".sd", ".sdf", "SMILES strings"],
        "output_format": "SDF (.sd) with energy annotations",
        "default_conformers": 250,
        "default_max_iters": 100,
        "port": 3004
    }


# Mount the MCP SSE app at root
app = Starlette(routes=[
    Mount("/", app=mcp.sse_app()),
])

if __name__ == "__main__":
    # Listen on all interfaces, port 3004 (different from gen_conf_server on 3003)
    print("Starting nvMolKit GPU Conformation Server on port 3004...")
    uvicorn.run(app, host="0.0.0.0", port=3004)
