from langchain_community.tools.ddg_search import DuckDuckGoSearchRun
from langchain_core.tools import Tool

search_tool = DuckDuckGoSearchRun()

browser_tool = Tool(
    name="web_search",
    func=search_tool.run,
    description="""
    A tool to search the internet for information.
    Use this to find facts, data, code examples, or any other information
    needed to complete the user's request.
    Input should be a clear and concise search query.
    """
)