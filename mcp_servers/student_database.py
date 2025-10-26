"""
StudentDatabaseModule - A thread-safe centralized database interface for student records.

This module provides a SQLite-based database interface that can be used by multiple
MCP servers to ensure data consistency and synchronization.

SINGLETON PATTERN: Only one instance per database path exists.
"""

import sqlite3
import threading
import csv
import os
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from contextlib import contextmanager


class StudentDatabaseModule:
    """
    A thread-safe database module for managing student records (Singleton pattern).
    
    This class provides:
    - Thread-safe access to student records
    - CSV import/export functionality
    - Query execution and updates
    - Schema inspection
    - Common database statistics
    
    Singleton behavior: Only one instance per unique database path.
    """
    
    _instances = {}  # Dictionary to store instances by db_path
    _instances_lock = threading.Lock()  # Lock for instance creation
    
    def __new__(cls, db_path: str = "student_records.db", csv_file: Optional[str] = None):
        """
        Create or return existing instance (Singleton pattern).
        
        Args:
            db_path: Path to the SQLite database file
            csv_file: Optional path to CSV file for initial data load (only used on first creation)
        
        Returns:
            Singleton instance for the given db_path
        """
        # Normalize path for consistent comparison
        normalized_path = os.path.abspath(db_path)
        
        with cls._instances_lock:
            if normalized_path not in cls._instances:
                # Create new instance
                instance = super(StudentDatabaseModule, cls).__new__(cls)
                cls._instances[normalized_path] = instance
                
                # Flag to indicate this is a new instance that needs initialization
                instance._initialized = False
            
            return cls._instances[normalized_path]
    
    def __init__(self, db_path: str = "student_records.db", csv_file: Optional[str] = None):
        """
        Initialize the database module (only runs once per unique db_path).
        
        Args:
            db_path: Path to the SQLite database file
            csv_file: Optional path to CSV file for initial data load
        """
        # Only initialize once
        if self._initialized:
            return
        
        self.db_path = os.path.abspath(db_path)
        self.lock = threading.RLock()  # Reentrant lock for thread safety
        self._local = threading.local()  # Thread-local storage for connections
        
        # Initialize database and create table if it doesn't exist
        self._initialize_database()
        
        # Load data from CSV if provided
        if csv_file and os.path.exists(csv_file):
            self.load_from_csv(csv_file)
        
        self._initialized = True
    
    @classmethod
    def get_instance(cls, db_path: str = "student_records.db") -> 'StudentDatabaseModule':
        """
        Get the singleton instance for a database path.
        
        Args:
            db_path: Path to the SQLite database file
        
        Returns:
            Singleton instance for the given db_path
        """
        return cls(db_path)
    
    @classmethod
    def clear_instances(cls):
        """
        Clear all singleton instances (useful for testing).
        Warning: This should only be used in testing scenarios.
        """
        with cls._instances_lock:
            # Close all connections first
            for instance in cls._instances.values():
                try:
                    instance.close()
                except:
                    pass
            cls._instances.clear()
    
    @contextmanager
    def _get_connection(self):
        """
        Get a thread-local database connection with automatic cleanup.
        
        Yields:
            sqlite3.Connection: Database connection
        """
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._local.connection.row_factory = sqlite3.Row  # Enable column access by name
        
        try:
            yield self._local.connection
        except Exception as e:
            self._local.connection.rollback()
            raise e
    
    def _initialize_database(self):
        """Initialize the database and create the students table if it doesn't exist."""
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS students (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        first_name TEXT NOT NULL,
                        last_name TEXT NOT NULL,
                        gender TEXT,
                        date_of_birth TEXT,
                        class TEXT,
                        email TEXT UNIQUE,
                        phone TEXT,
                        major TEXT,
                        gpa REAL,
                        test_i REAL,
                        test_ii REAL,
                        test_iii REAL,
                        test_iv REAL,
                        middle_term_exam REAL,
                        final_exam REAL,
                        final_score TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create index on email for faster lookups
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_email ON students(email)
                """)
                
                # Create index on last_name for faster searches
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_last_name ON students(last_name)
                """)
                
                conn.commit()
    
    def execute_query(self, query: str, params: Optional[Tuple] = None, fetch: bool = True) -> List[Dict[str, Any]]:
        """
        Execute a SQL query and return results.
        
        Args:
            query: SQL query string
            params: Optional tuple of parameters for parameterized queries
            fetch: Whether to fetch and return results (True for SELECT, False for INSERT/UPDATE/DELETE)
        
        Returns:
            List of dictionaries representing rows (if fetch=True), empty list otherwise
        """
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                if fetch:
                    rows = cursor.fetchall()
                    # Convert sqlite3.Row objects to dictionaries
                    return [dict(row) for row in rows]
                else:
                    conn.commit()
                    return []
    
    def update_student(self, email: str, updates: Dict[str, Any]) -> bool:
        """
        Update a student record by email.
        
        Args:
            email: Student email address
            updates: Dictionary of field names and values to update
        
        Returns:
            True if update was successful, False otherwise
        """
        if not updates:
            return False
        
        # Build UPDATE query dynamically
        set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
        values = list(updates.values())
        values.append(email)  # Add email for WHERE clause
        
        query = f"""
            UPDATE students 
            SET {set_clause}, updated_at = CURRENT_TIMESTAMP
            WHERE email = ?
        """
        
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, values)
                conn.commit()
                return cursor.rowcount > 0
    
    def add_student(self, student_data: Dict[str, Any]) -> Optional[int]:
        """
        Add a new student record.
        
        Args:
            student_data: Dictionary containing student information
        
        Returns:
            The ID of the newly inserted student, or None if insertion failed
        """
        required_fields = ['first_name', 'last_name', 'email']
        if not all(field in student_data for field in required_fields):
            raise ValueError(f"Missing required fields: {required_fields}")
        
        fields = list(student_data.keys())
        placeholders = ", ".join(["?" for _ in fields])
        field_names = ", ".join(fields)
        values = [student_data[field] for field in fields]
        
        query = f"""
            INSERT INTO students ({field_names})
            VALUES ({placeholders})
        """
        
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(query, values)
                    conn.commit()
                    return cursor.lastrowid
                except sqlite3.IntegrityError as e:
                    # Email already exists or other constraint violation
                    print(f"Error adding student: {e}")
                    return None
    
    def delete_student(self, email: str) -> bool:
        """
        Delete a student record by email.
        
        Args:
            email: Student email address
        
        Returns:
            True if deletion was successful, False otherwise
        """
        query = "DELETE FROM students WHERE email = ?"
        
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (email,))
                conn.commit()
                return cursor.rowcount > 0
    
    def get_table_schema(self) -> List[Dict[str, Any]]:
        """
        Get the schema of the students table.
        
        Returns:
            List of dictionaries containing column information
        """
        query = "PRAGMA table_info(students)"
        with self.lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
    
    def get_total_records(self) -> int:
        """
        Get the total number of student records.
        
        Returns:
            Total number of records
        """
        query = "SELECT COUNT(*) as count FROM students"
        result = self.execute_query(query)
        return result[0]['count'] if result else 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get various statistics about the student database.
        
        Returns:
            Dictionary containing statistics
        """
        stats = {
            'total_records': self.get_total_records(),
            'average_gpa': None,
            'major_distribution': {},
            'class_distribution': {}
        }
        
        # Average GPA
        gpa_query = "SELECT AVG(gpa) as avg_gpa FROM students WHERE gpa IS NOT NULL"
        result = self.execute_query(gpa_query)
        if result and result[0]['avg_gpa'] is not None:
            stats['average_gpa'] = round(result[0]['avg_gpa'], 2)
        
        # Major distribution
        major_query = "SELECT major, COUNT(*) as count FROM students WHERE major IS NOT NULL GROUP BY major"
        major_results = self.execute_query(major_query)
        stats['major_distribution'] = {row['major']: row['count'] for row in major_results}
        
        # Class distribution
        class_query = "SELECT class, COUNT(*) as count FROM students WHERE class IS NOT NULL GROUP BY class"
        class_results = self.execute_query(class_query)
        stats['class_distribution'] = {row['class']: row['count'] for row in class_results}
        
        return stats
    
    def load_from_csv(self, csv_file: str, clear_existing: bool = False) -> int:
        """
        Load student records from a CSV file.
        
        Args:
            csv_file: Path to the CSV file
            clear_existing: Whether to clear existing records before loading
        
        Returns:
            Number of records loaded
        """
        if not os.path.exists(csv_file):
            raise FileNotFoundError(f"CSV file not found: {csv_file}")
        
        with self.lock:
            # Clear existing records if requested
            if clear_existing:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM students")
                    conn.commit()
            
            records_loaded = 0
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    # Map CSV headers to database fields
                    student_data = {
                        'first_name': row.get('First Name', ''),
                        'last_name': row.get('Last Name', ''),
                        'gender': row.get('Gender', ''),
                        'date_of_birth': row.get('Date of Birth', ''),
                        'class': row.get('Class', ''),
                        'email': row.get('Email', ''),
                        'phone': row.get('Phone', ''),
                        'major': row.get('Major', ''),
                        'gpa': self._parse_float(row.get('GPA')),
                        'test_i': self._parse_float(row.get('Test-I')),
                        'test_ii': self._parse_float(row.get('Test-II')),
                        'test_iii': self._parse_float(row.get('Test-III')),
                        'test_iv': self._parse_float(row.get('Test-IV')),
                        'middle_term_exam': self._parse_float(row.get('Middle Term Exam')),
                        'final_exam': self._parse_float(row.get('Final Exam')),
                        'final_score': row.get('Final Score', '')
                    }
                    
                    # Try to add student (will skip if email already exists)
                    if self.add_student(student_data):
                        records_loaded += 1
            
            return records_loaded
    
    def export_to_csv(self, csv_file: str) -> int:
        """
        Export all student records to a CSV file.
        
        Args:
            csv_file: Path to the output CSV file
        
        Returns:
            Number of records exported
        """
        query = """
            SELECT first_name, last_name, gender, date_of_birth, class, email, 
                   phone, major, gpa, test_i, test_ii, test_iii, test_iv,
                   middle_term_exam, final_exam, final_score
            FROM students
            ORDER BY last_name, first_name
        """
        
        records = self.execute_query(query)
        
        if not records:
            return 0
        
        # Map database fields to CSV headers
        fieldnames = [
            'First Name', 'Last Name', 'Gender', 'Date of Birth', 'Class',
            'Email', 'Phone', 'Major', 'GPA', 'Test-I', 'Test-II', 'Test-III',
            'Test-IV', 'Middle Term Exam', 'Final Exam', 'Final Score'
        ]
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for record in records:
                csv_row = {
                    'First Name': record['first_name'],
                    'Last Name': record['last_name'],
                    'Gender': record['gender'],
                    'Date of Birth': record['date_of_birth'],
                    'Class': record['class'],
                    'Email': record['email'],
                    'Phone': record['phone'],
                    'Major': record['major'],
                    'GPA': record['gpa'],
                    'Test-I': record['test_i'],
                    'Test-II': record['test_ii'],
                    'Test-III': record['test_iii'],
                    'Test-IV': record['test_iv'],
                    'Middle Term Exam': record['middle_term_exam'],
                    'Final Exam': record['final_exam'],
                    'Final Score': record['final_score']
                }
                writer.writerow(csv_row)
        
        return len(records)
    
    def reload_from_csv(self, csv_file: str) -> int:
        """
        Reload the database from a CSV file (clears existing data).
        
        Args:
            csv_file: Path to the CSV file
        
        Returns:
            Number of records loaded
        """
        return self.load_from_csv(csv_file, clear_existing=True)
    
    def search_students(self, **criteria) -> List[Dict[str, Any]]:
        """
        Search for students based on various criteria.
        
        Args:
            **criteria: Keyword arguments for search criteria (e.g., major='Biology', gpa=3.5)
        
        Returns:
            List of matching student records
        """
        if not criteria:
            return self.execute_query("SELECT * FROM students")
        
        where_clauses = []
        values = []
        
        for key, value in criteria.items():
            if value is not None:
                where_clauses.append(f"{key} = ?")
                values.append(value)
        
        if not where_clauses:
            return []
        
        query = f"SELECT * FROM students WHERE {' AND '.join(where_clauses)}"
        return self.execute_query(query, tuple(values))
    
    def get_student_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get a student record by email address.
        
        Args:
            email: Student email address
        
        Returns:
            Student record dictionary or None if not found
        """
        query = "SELECT * FROM students WHERE email = ?"
        results = self.execute_query(query, (email,))
        return results[0] if results else None
    
    def close(self):
        """Close the database connection for the current thread."""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
    
    @staticmethod
    def _parse_float(value: Any) -> Optional[float]:
        """
        Safely parse a value to float.
        
        Args:
            value: Value to parse
        
        Returns:
            Float value or None if parsing fails
        """
        if value is None or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
    
    def __repr__(self):
        """String representation showing singleton status."""
        return f"<StudentDatabaseModule(db_path='{self.db_path}', singleton_id={id(self)})>"


# Example usage
if __name__ == "__main__":
    # Initialize database with CSV file
    db1 = StudentDatabaseModule(
        db_path="student_records.db",
        csv_file="student_genchem_records.csv"
    )
    
    # This returns the SAME instance
    db2 = StudentDatabaseModule(db_path="student_records.db")
    
    print(f"db1 is db2: {db1 is db2}")  # True - Same instance!
    print(f"db1 id: {id(db1)}")
    print(f"db2 id: {id(db2)}")
    
    print(f"\nTotal records: {db1.get_total_records()}")
    print("\nStatistics:")
    stats = db1.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Close connection
    db1.close()
