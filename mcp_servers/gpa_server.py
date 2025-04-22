from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount
import uvicorn

# Create an MCP server with increased timeout
mcp = FastMCP("gpa_server")

# Define our tool
@mcp.tool()
def check_student_gpa(student_name: str) -> any:
    """Check a student's GPA by student's name. Return 0 if not found."""
    gpa_dict = {"John Lee": 3.7, "Jenny Lin": 3.8, "Bob Johnson": 4.0, "Robert Brown": 3.5, "Amy Smith": 3.6}
    try:
        # Add robust error handling
        if not isinstance(student_name, str):
            return "No student name is provided"
        if student_name in gpa_dict:
            return gpa_dict[student_name]
        else:
            # check if the first name is in the dictionary
            first_name = student_name.split()[0]
            for name in gpa_dict.keys():
                if name.startswith(first_name):
                    return gpa_dict[name]
        # If not found, return 0
        return "Could not find the student in the dictionary"
    except KeyError:
        # Return 0 on any error
        return "Could not find the student in the dictionary"
    except TypeError:
        # Return 0 on any error
        return "Could not find the student in the dictionary"
    except ValueError:
        # Return 0 on any error
        return "Could not find the student in the dictionary"

    except Exception as e:
        # Return 0 on any error
        return 0

@mcp.tool()
def off_school_request(off_type, start_date: str, end_date) -> any:
    """Off school request with off type, start date and end date for the off_school.
    args:
       off_type: the off_school type (sick time, field trip or college visit).
       start_date: the off school starting date. The date will be in mm-dd-yyyy format. For example 05-10-2025.
       end_date: the off school ending date. The date should also be in mm-dd-yyyy format. 
    return:
       a json string like {"off_type": "college visit", "start_date": "04-23-2025", "end_date": "04-26-2025"}
    """
    return {"off_type": off_type, "start_date": start_date, "end_date": end_date}


# Mount the MCP SSE app at root
app = Starlette(routes=[
    Mount("/", app=mcp.sse_app()),
])

if __name__ == "__main__":
    # Listen on all interfaces, port 3000
    uvicorn.run(app, host="0.0.0.0", port=3000)
