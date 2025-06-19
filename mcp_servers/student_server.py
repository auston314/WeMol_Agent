from mcp.server.fastmcp import FastMCP

# Demo dataset of student records
STUDENT_RECORDS = [
    {"full_name": "John Smith", "gender": "Male", "date_of_birth": "2009-01-15", "grade": "10", "email": "john.smith@example.com", "school_name": "Springfield High"},
    {"full_name": "Bob Johnson", "gender": "Male", "date_of_birth": "2010-03-22", "grade": "9", "email": "bob.johnson@example.com", "school_name": "Springfield High"},
    {"full_name": "Amy Zhu", "gender": "Female", "date_of_birth": "2009-07-09", "grade": "10", "email": "amy.zhu@example.com", "school_name": "Springfield High"},
    # Add 17 more demo records here
    {"full_name": "Alice Brown", "gender": "Female", "date_of_birth": "2011-05-12", "grade": "8", "email": "alice.brown@example.com", "school_name": "Springfield High"},
    {"full_name": "Charlie Davis", "gender": "Male", "date_of_birth": "2008-11-30", "grade": "11", "email": "charlie.davis@example.com", "school_name": "Springfield High"},
    {"full_name": "Diana Evans", "gender": "Female", "date_of_birth": "2010-02-18", "grade": "9", "email": "diana.evans@example.com", "school_name": "Springfield High"},
    {"full_name": "Ethan Foster", "gender": "Male", "date_of_birth": "2009-08-25", "grade": "10", "email": "ethan.foster@example.com", "school_name": "Springfield High"},
    {"full_name": "Fiona Green", "gender": "Female", "date_of_birth": "2011-04-10", "grade": "8", "email": "fiona.green@example.com", "school_name": "Springfield High"},
    {"full_name": "George Harris", "gender": "Male", "date_of_birth": "2008-09-14", "grade": "11", "email": "george.harris@example.com", "school_name": "Springfield High"},
    {"full_name": "Hannah Irving", "gender": "Female", "date_of_birth": "2010-12-03", "grade": "9", "email": "hannah.irving@example.com", "school_name": "Springfield High"},
    {"full_name": "Ian Jackson", "gender": "Male", "date_of_birth": "2009-06-21", "grade": "10", "email": "ian.jackson@example.com", "school_name": "Springfield High"},
    {"full_name": "Julia King", "gender": "Female", "date_of_birth": "2011-03-15", "grade": "8", "email": "julia.king@example.com", "school_name": "Springfield High"},
    {"full_name": "Kevin Lee", "gender": "Male", "date_of_birth": "2008-10-05", "grade": "11", "email": "kevin.lee@example.com", "school_name": "Springfield High"},
    {"full_name": "Laura Martinez", "gender": "Female", "date_of_birth": "2010-01-28", "grade": "9", "email": "laura.martinez@example.com", "school_name": "Springfield High"},
    {"full_name": "Michael Nelson", "gender": "Male", "date_of_birth": "2009-09-17", "grade": "10", "email": "michael.nelson@example.com", "school_name": "Springfield High"},
    {"full_name": "Nina Owens", "gender": "Female", "date_of_birth": "2011-06-11", "grade": "8", "email": "nina.owens@example.com", "school_name": "Springfield High"},
    {"full_name": "Oscar Perez", "gender": "Male", "date_of_birth": "2008-12-20", "grade": "11", "email": "oscar.perez@example.com", "school_name": "Springfield High"},
    {"full_name": "Paula Quinn", "gender": "Female", "date_of_birth": "2010-03-08", "grade": "9", "email": "paula.quinn@example.com", "school_name": "Springfield High"},
    {"full_name": "Ryan Scott", "gender": "Male", "date_of_birth": "2009-07-30", "grade": "10", "email": "ryan.scott@example.com", "school_name": "Springfield High"},
    {"full_name": "Sophia Taylor", "gender": "Female", "date_of_birth": "2011-02-22", "grade": "8", "email": "sophia.taylor@example.com", "school_name": "Springfield High"}
]

mcp = FastMCP("student_record_server")

@mcp.tool()
def get_student_record(full_name: str):
    """Retrieve a student's record by full name."""
    for record in STUDENT_RECORDS:
        if record["full_name"].lower() == full_name.lower():
            return f"Here is the student record of {full_name} {record}"
    return f"No student record can be found for the name: {full_name}"

if __name__ == "__main__":
    mcp.run()
