from langchain_experimental.tools import PythonREPLTool
from langchain_core.tools import Tool

python_repl_tool = PythonREPLTool()

code_interpreter_tool = Tool(
    name="python_interpreter",
    func=python_repl_tool.run,
    description="""
    A Python REPL (Read-Eval-Print Loop) tool.
    Use this to execute Python code when a task requires it.
    The input should be a valid Python code snippet.
    The tool will return the standard output of the executed code.
    You can use this to perform calculations, manipulate data, or any other
    programming task. DO not include the 'python' markdown tag in your code.
    """
)