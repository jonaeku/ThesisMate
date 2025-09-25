import requests
import os
from typing import Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class GitHubClient:
    def __init__(self):
        self.github_url = os.getenv("GITHUB_URL")
        self.github_token = os.getenv("GITHUB_TOKEN")

    def get_repo_content(self) -> Any:
        """
        Fetch and print the content of the repository specified in the .env file.
        return JSON response with all repository content from GitHub API
        retrieve data e.g.:
            for item in repo_content:
                name = item.get("name", "N/A")
                path = item.get("path", "N/A")
                item_type = item.get("type", "N/A")
        Docu: https://docs.github.com/en/rest/repos/contents?apiVersion=2022-11-28&versionId=free-pro-team%40latest&category=commits&subcategory=commits#get-repository-content
        """
        url = f"{self.github_url}/contents"
        headers = {"Authorization": f"token {self.github_token}"} if self.github_token else {}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            return response.json()
        else:
            print("Error:", response.status_code, response.text)

    def get_commit_history(self) -> Any:
        """
        Fetch and print the last 5 commits of the repository specified in the .env file.
        return JSON response with all commits from GitHub API
        retrieve data e.g.:
            sha = commit["sha"]
            message = commit["commit"]["message"]
            author = commit["commit"]["author"]["name"]
            date = commit["commit"]["author"]["date"]
        Docu: https://docs.github.com/en/rest/commits/commits?apiVersion=2022-11-28#list-commits
        """
        url = f"{self.github_url}/commits"
        headers = {"Authorization": f"token {self.github_token}"} if self.github_token else {}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            return response.json()
        else:
            print("Error:", response.status_code, response.text)


# Test Examples:

# if __name__ == "__main__":
#     client = GitHubClient()
#     try:
#         commits = client.get_commit_history()
#         print("Commit History:")
#         for commit in commits[:5]:
#             sha = commit["sha"]
#             message = commit["commit"]["message"]
#             author = commit["commit"]["author"]["name"]
#             date = commit["commit"]["author"]["date"]
#             print(f"{sha[:7]} | {author} | {date} | {message}")
#     except Exception as e:
#         print(f"Error: {e}")
#
#
#     try:
#         repo_content = client.get_repo_content()
#         print("Repository Content:")
#         for item in repo_content:
#             name = item.get("name", "N/A")
#             path = item.get("path", "N/A")
#             item_type = item.get("type", "N/A")
#             print(f"Name: {name}, Path: {path}, Type: {item_type}")
#     except Exception as e:
#         print(f"Error: {e}")
