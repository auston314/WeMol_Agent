"""
Student SQL MCP Server - Execute SQL queries on student database

This MCP server provides SQL query execution capabilities for the student database,
along with helpful utilities like schema inspection and example queries.

Features:
- Execute arbitrary SQL queries (SELECT only for safety)
- Get database schema information
- Get example SQL queries
- Get database statistics
- Thread-safe database access using StudentDatabaseModule

Port: 3001
"""

import asyncio
import logging
from typing import Any
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)
from pydantic import AnyUrl
import mcp.types as types

# Import the singleton database module
from student_database import StudentDatabaseModule

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("student_sql_server")

# Initialize the database module (singleton)
db = StudentDatabaseModule(
    db_path="student_records.db",
    csv_file="student_genchem_records.csv"
)

# Create the MCP server
server = Server("student_sql_server")

# Store server capabilities
server_capabilities = {
    "tools": {},
    "resources": {},
    "prompts": {}
}


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """
    List available tools for SQL operations on the student database.
    
    Returns:
        List of available tools
    """
    return [
        Tool(
            name="execute_sql_query",
            description="""Execute a SQL SELECT query on the student database and return results.
            
IMPORTANT SAFETY NOTES:
- Only SELECT queries are allowed for data safety
- Queries are executed in read-only mode
- Use parameterized queries to prevent SQL injection

Available tables:
- students: Main student records table

Common query patterns:
- SELECT * FROM students WHERE condition
- SELECT column1, column2 FROM students
- SELECT COUNT(*), AVG(gpa) FROM students
- SELECT * FROM students ORDER BY field LIMIT n

Examples:
- Find students with GPA > 3.5: "SELECT * FROM students WHERE gpa > 3.5"
- Get average test scores: "SELECT AVG(test_i) as avg_test1 FROM students"
- Count by major: "SELECT major, COUNT(*) as count FROM students GROUP BY major"
            """,
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL SELECT query to execute (e.g., 'SELECT * FROM students WHERE gpa > 3.5')"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_database_schema",
            description="""Get the complete schema information for the student database.
            
Returns detailed information about:
- Table structure (columns, types, constraints)
- Available indexes
- Column descriptions
- Sample data format

This is useful for:
- Understanding what data is available
- Writing correct SQL queries
- Knowing valid column names and types
- Understanding relationships between fields
            """,
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_sql_examples",
            description="""Get a collection of useful SQL query examples for the student database.
            
Returns ready-to-use SQL queries for common tasks:
- Finding students by various criteria (GPA, major, class, etc.)
- Calculating statistics (averages, counts, min/max)
- Grouping and aggregating data
- Sorting and filtering results
- Complex queries with multiple conditions

These examples can be:
- Used directly by modifying parameters
- Combined to create more complex queries
- Used as learning references for SQL syntax
            """,
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_database_stats",
            description="""Get comprehensive statistics about the student database.
            
Returns useful information:
- Total number of students
- Number of unique majors
- GPA statistics (min, max, average)
- Test score averages
- Class distribution
- Gender distribution
- Other summary statistics

This provides a quick overview of the database contents without writing queries.
            """,
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_table_preview",
            description="""Get a preview of the student table with sample records.
            
Returns:
- Column names and types
- First few records from the database
- Total record count

Useful for:
- Quickly seeing what data looks like
- Understanding data format
- Checking if database has data
            """,
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of records to preview (default: 5, max: 20)",
                        "default": 5
                    }
                },
                "required": []
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, 
    arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    
    Args:
        name: Name of the tool to execute
        arguments: Tool arguments
    
    Returns:
        List of content objects with results
    """
    try:
        if name == "execute_sql_query":
            return await execute_sql_query(arguments)
        elif name == "get_database_schema":
            return await get_database_schema(arguments)
        elif name == "get_sql_examples":
            return await get_sql_examples(arguments)
        elif name == "get_database_stats":
            return await get_database_stats(arguments)
        elif name == "get_table_preview":
            return await get_table_preview(arguments)
        else:
            raise ValueError(f"Unknown tool: {name}")
    except Exception as e:
        logger.error(f"Error executing tool {name}: {str(e)}")
        return [types.TextContent(
            type="text",
            text=f"Error: {str(e)}"
        )]


async def execute_sql_query(arguments: dict | None) -> list[types.TextContent]:
    """
    Execute a SQL SELECT query on the student database.
    
    Args:
        arguments: Dictionary containing 'query' key
    
    Returns:
        Query results as formatted text
    """
    if not arguments or "query" not in arguments:
        return [types.TextContent(
            type="text",
            text="Error: Missing 'query' parameter"
        )]
    
    query = arguments["query"].strip()
    
    # Safety check: Only allow SELECT queries
    if not query.upper().startswith("SELECT"):
        return [types.TextContent(
            type="text",
            text="Error: Only SELECT queries are allowed for safety reasons. "
                 "Use SELECT to read data from the database."
        )]
    
    try:
        # Execute the query
        results = db.execute_query(query, fetch=True)
        
        if not results:
            return [types.TextContent(
                type="text",
                text="Query executed successfully. No results returned (0 rows)."
            )]
        
        # Format results as a readable table
        result_text = f"Query executed successfully. Found {len(results)} row(s).\n\n"
        
        # Get column names from first result
        columns = list(results[0].keys())
        
        # Create header
        result_text += "Results:\n"
        result_text += "-" * 80 + "\n"
        result_text += " | ".join(columns) + "\n"
        result_text += "-" * 80 + "\n"
        
        # Add rows (limit to first 100 for readability)
        display_limit = min(len(results), 100)
        for row in results[:display_limit]:
            row_values = [str(row[col]) if row[col] is not None else "NULL" for col in columns]
            result_text += " | ".join(row_values) + "\n"
        
        if len(results) > display_limit:
            result_text += f"\n... ({len(results) - display_limit} more rows not shown)"
        
        result_text += "-" * 80 + "\n"
        result_text += f"\nTotal rows: {len(results)}"
        
        return [types.TextContent(
            type="text",
            text=result_text
        )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"Error executing query: {str(e)}\n\n"
                 f"Query: {query}\n\n"
                 f"Tip: Use get_database_schema to see available columns and tables."
        )]


async def get_database_schema(arguments: dict | None) -> list[types.TextContent]:
    """
    Get the database schema information.
    
    Returns:
        Schema information as formatted text
    """
    try:
        # Get table info
        schema_query = "PRAGMA table_info(students)"
        schema_info = db.execute_query(schema_query, fetch=True)
        
        # Get indexes
        index_query = "PRAGMA index_list(students)"
        indexes = db.execute_query(index_query, fetch=True)
        
        schema_text = "📊 STUDENT DATABASE SCHEMA\n"
        schema_text += "=" * 80 + "\n\n"
        
        schema_text += "Table: students\n"
        schema_text += "-" * 80 + "\n\n"
        
        schema_text += "Columns:\n"
        for col in schema_info:
            col_name = col['name']
            col_type = col['type']
            not_null = " NOT NULL" if col['notnull'] else ""
            pk = " PRIMARY KEY" if col['pk'] else ""
            default = f" DEFAULT {col['dflt_value']}" if col['dflt_value'] else ""
            
            schema_text += f"  • {col_name:<20} {col_type:<10} {not_null}{pk}{default}\n"
        
        schema_text += "\n" + "-" * 80 + "\n\n"
        
        schema_text += "Column Descriptions:\n"
        schema_text += "  • id: Auto-incrementing primary key\n"
        schema_text += "  • first_name: Student's first name\n"
        schema_text += "  • last_name: Student's last name\n"
        schema_text += "  • gender: Student's gender\n"
        schema_text += "  • date_of_birth: Birth date (YYYY-MM-DD format)\n"
        schema_text += "  • class: Graduating class (e.g., 'Class 2027')\n"
        schema_text += "  • email: Student email (unique identifier)\n"
        schema_text += "  • phone: Contact phone number\n"
        schema_text += "  • major: Academic major\n"
        schema_text += "  • gpa: Grade Point Average (0.0-4.0)\n"
        schema_text += "  • test_i: Test I score (0-100)\n"
        schema_text += "  • test_ii: Test II score (0-100)\n"
        schema_text += "  • test_iii: Test III score (0-100)\n"
        schema_text += "  • test_iv: Test IV score (0-100)\n"
        schema_text += "  • middle_term_exam: Midterm exam score (0-100)\n"
        schema_text += "  • final_exam: Final exam score (0-100)\n"
        schema_text += "  • final_score: Final letter grade (A+, A, B+, B, etc.)\n"
        schema_text += "  • created_at: Record creation timestamp\n"
        schema_text += "  • updated_at: Last update timestamp\n"
        
        if indexes:
            schema_text += "\n" + "-" * 80 + "\n\n"
            schema_text += "Indexes:\n"
            for idx in indexes:
                schema_text += f"  • {idx['name']}: {idx['unique'] and 'UNIQUE' or 'INDEX'}\n"
        
        schema_text += "\n" + "=" * 80 + "\n"
        
        return [types.TextContent(
            type="text",
            text=schema_text
        )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"Error retrieving schema: {str(e)}"
        )]


async def get_sql_examples(arguments: dict | None) -> list[types.TextContent]:
    """
    Get example SQL queries for the student database.
    
    Returns:
        Collection of example queries
    """
    examples = """📚 SQL QUERY EXAMPLES FOR STUDENT DATABASE
""" + "=" * 80 + """

1️⃣ BASIC QUERIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Get all students:
    SELECT * FROM students

Get specific columns:
    SELECT first_name, last_name, email, gpa FROM students

Get first 10 students:
    SELECT * FROM students LIMIT 10


2️⃣ FILTERING QUERIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Students with high GPA (>= 3.5):
    SELECT first_name, last_name, gpa FROM students WHERE gpa >= 3.5

Students by major:
    SELECT * FROM students WHERE major = 'Biology'

Students in specific class:
    SELECT * FROM students WHERE class = 'Class 2027'

Students with excellent final exam (>= 90):
    SELECT first_name, last_name, final_exam FROM students WHERE final_exam >= 90

Multiple conditions (AND):
    SELECT * FROM students WHERE gpa > 3.0 AND major = 'Chemistry'

Multiple conditions (OR):
    SELECT * FROM students WHERE major = 'Biology' OR major = 'Chemistry'

Pattern matching (LIKE):
    SELECT * FROM students WHERE email LIKE '%@calstate.edu'
    SELECT * FROM students WHERE last_name LIKE 'S%'


3️⃣ SORTING QUERIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Sort by GPA (highest first):
    SELECT first_name, last_name, gpa FROM students ORDER BY gpa DESC

Sort by last name (alphabetical):
    SELECT * FROM students ORDER BY last_name ASC

Sort by multiple columns:
    SELECT * FROM students ORDER BY class ASC, gpa DESC


4️⃣ AGGREGATE FUNCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Count total students:
    SELECT COUNT(*) as total_students FROM students

Average GPA:
    SELECT AVG(gpa) as average_gpa FROM students

Highest and lowest GPA:
    SELECT MAX(gpa) as highest_gpa, MIN(gpa) as lowest_gpa FROM students

Average test scores:
    SELECT 
        AVG(test_i) as avg_test1,
        AVG(test_ii) as avg_test2,
        AVG(test_iii) as avg_test3,
        AVG(test_iv) as avg_test4
    FROM students


5️⃣ GROUPING QUERIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Count students by major:
    SELECT major, COUNT(*) as student_count 
    FROM students 
    GROUP BY major 
    ORDER BY student_count DESC

Average GPA by major:
    SELECT major, AVG(gpa) as avg_gpa 
    FROM students 
    GROUP BY major 
    ORDER BY avg_gpa DESC

Count by class year:
    SELECT class, COUNT(*) as count 
    FROM students 
    GROUP BY class 
    ORDER BY class

Gender distribution:
    SELECT gender, COUNT(*) as count 
    FROM students 
    GROUP BY gender

Grade distribution:
    SELECT final_score, COUNT(*) as count 
    FROM students 
    GROUP BY final_score 
    ORDER BY count DESC


6️⃣ ADVANCED QUERIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Students performing above average:
    SELECT first_name, last_name, gpa 
    FROM students 
    WHERE gpa > (SELECT AVG(gpa) FROM students)

Top 10 students by GPA:
    SELECT first_name, last_name, gpa 
    FROM students 
    ORDER BY gpa DESC 
    LIMIT 10

Students with all test scores above 80:
    SELECT first_name, last_name 
    FROM students 
    WHERE test_i > 80 AND test_ii > 80 AND test_iii > 80 AND test_iv > 80

Calculate average of all tests per student:
    SELECT 
        first_name, 
        last_name,
        (test_i + test_ii + test_iii + test_iv) / 4.0 as avg_test_score
    FROM students
    ORDER BY avg_test_score DESC

Students at risk (GPA < 2.5):
    SELECT first_name, last_name, email, gpa 
    FROM students 
    WHERE gpa < 2.5 
    ORDER BY gpa ASC


7️⃣ STATISTICAL QUERIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Comprehensive statistics:
    SELECT 
        COUNT(*) as total,
        AVG(gpa) as avg_gpa,
        MIN(gpa) as min_gpa,
        MAX(gpa) as max_gpa,
        AVG(final_exam) as avg_final
    FROM students

Majors with highest average GPA:
    SELECT 
        major, 
        COUNT(*) as student_count,
        AVG(gpa) as avg_gpa,
        MAX(gpa) as max_gpa
    FROM students 
    GROUP BY major 
    HAVING student_count >= 3
    ORDER BY avg_gpa DESC


""" + "=" * 80 + """

💡 TIPS:
- Always use SELECT for read-only queries
- Use WHERE to filter results
- Use ORDER BY to sort results
- Use LIMIT to restrict number of results
- Use GROUP BY with aggregate functions (COUNT, AVG, MIN, MAX)
- Use HAVING to filter grouped results
"""

    return [types.TextContent(
        type="text",
        text=examples
    )]


async def get_database_stats(arguments: dict | None) -> list[types.TextContent]:
    """
    Get comprehensive database statistics.
    
    Returns:
        Statistics as formatted text
    """
    try:
        # Get various statistics
        stats_text = "📊 STUDENT DATABASE STATISTICS\n"
        stats_text += "=" * 80 + "\n\n"
        
        # Total students
        total = db.execute_query("SELECT COUNT(*) as count FROM students", fetch=True)
        stats_text += f"📚 Total Students: {total[0]['count']}\n\n"
        
        # GPA statistics
        gpa_stats = db.execute_query(
            "SELECT MIN(gpa) as min, MAX(gpa) as max, AVG(gpa) as avg FROM students",
            fetch=True
        )
        stats_text += "🎓 GPA Statistics:\n"
        stats_text += f"  • Minimum: {gpa_stats[0]['min']:.2f}\n"
        stats_text += f"  • Maximum: {gpa_stats[0]['max']:.2f}\n"
        stats_text += f"  • Average: {gpa_stats[0]['avg']:.2f}\n\n"
        
        # Major distribution
        majors = db.execute_query(
            "SELECT major, COUNT(*) as count FROM students GROUP BY major ORDER BY count DESC",
            fetch=True
        )
        stats_text += "🔬 Students by Major:\n"
        for major in majors:
            stats_text += f"  • {major['major']}: {major['count']} students\n"
        stats_text += "\n"
        
        # Class distribution
        classes = db.execute_query(
            "SELECT class, COUNT(*) as count FROM students GROUP BY class ORDER BY class",
            fetch=True
        )
        stats_text += "📅 Students by Class Year:\n"
        for cls in classes:
            stats_text += f"  • {cls['class']}: {cls['count']} students\n"
        stats_text += "\n"
        
        # Gender distribution
        genders = db.execute_query(
            "SELECT gender, COUNT(*) as count FROM students GROUP BY gender ORDER BY count DESC",
            fetch=True
        )
        stats_text += "👥 Gender Distribution:\n"
        for gender in genders:
            stats_text += f"  • {gender['gender']}: {gender['count']} students\n"
        stats_text += "\n"
        
        # Test score averages
        test_stats = db.execute_query(
            """SELECT 
                AVG(test_i) as avg_test1,
                AVG(test_ii) as avg_test2,
                AVG(test_iii) as avg_test3,
                AVG(test_iv) as avg_test4,
                AVG(middle_term_exam) as avg_midterm,
                AVG(final_exam) as avg_final
            FROM students""",
            fetch=True
        )
        stats_text += "📝 Average Test Scores:\n"
        stats_text += f"  • Test I:     {test_stats[0]['avg_test1']:.1f}\n"
        stats_text += f"  • Test II:    {test_stats[0]['avg_test2']:.1f}\n"
        stats_text += f"  • Test III:   {test_stats[0]['avg_test3']:.1f}\n"
        stats_text += f"  • Test IV:    {test_stats[0]['avg_test4']:.1f}\n"
        stats_text += f"  • Midterm:    {test_stats[0]['avg_midterm']:.1f}\n"
        stats_text += f"  • Final:      {test_stats[0]['avg_final']:.1f}\n\n"
        
        # Grade distribution
        grades = db.execute_query(
            "SELECT final_score, COUNT(*) as count FROM students GROUP BY final_score ORDER BY count DESC",
            fetch=True
        )
        stats_text += "📊 Final Grade Distribution:\n"
        for grade in grades:
            stats_text += f"  • {grade['final_score']}: {grade['count']} students\n"
        
        stats_text += "\n" + "=" * 80 + "\n"
        
        return [types.TextContent(
            type="text",
            text=stats_text
        )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"Error retrieving statistics: {str(e)}"
        )]


async def get_table_preview(arguments: dict | None) -> list[types.TextContent]:
    """
    Get a preview of the student table.
    
    Args:
        arguments: Dictionary with optional 'limit' parameter
    
    Returns:
        Table preview as formatted text
    """
    try:
        limit = 5
        if arguments and "limit" in arguments:
            limit = min(max(1, arguments["limit"]), 20)  # Between 1 and 20
        
        # Get total count
        total = db.execute_query("SELECT COUNT(*) as count FROM students", fetch=True)
        total_count = total[0]['count']
        
        # Get sample records
        query = f"SELECT * FROM students LIMIT {limit}"
        results = db.execute_query(query, fetch=True)
        
        preview_text = "👀 STUDENT TABLE PREVIEW\n"
        preview_text += "=" * 80 + "\n\n"
        preview_text += f"Total records in database: {total_count}\n"
        preview_text += f"Showing first {len(results)} record(s):\n\n"
        
        if results:
            # Show each record
            for i, record in enumerate(results, 1):
                preview_text += f"Record #{i}:\n"
                preview_text += "-" * 40 + "\n"
                for key, value in record.items():
                    if key not in ['id', 'created_at', 'updated_at']:  # Skip metadata
                        preview_text += f"  {key:20s}: {value}\n"
                preview_text += "\n"
        else:
            preview_text += "No records found in database.\n"
        
        preview_text += "=" * 80 + "\n"
        preview_text += "Use 'get_database_schema' to see all available columns.\n"
        preview_text += "Use 'execute_sql_query' to run custom queries.\n"
        
        return [types.TextContent(
            type="text",
            text=preview_text
        )]
    
    except Exception as e:
        return [types.TextContent(
            type="text",
            text=f"Error retrieving table preview: {str(e)}"
        )]


async def main():
    """Main entry point for the server."""
    logger.info("Starting Student SQL MCP Server on port 3001...")
    
    # Run the server using stdin/stdout streams
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="student_sql_server",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
