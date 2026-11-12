"""Concrete publication targets.

`git_pages` is the default and the only one implemented. Confluence, GitBook
and GitLab docs arrive here behind the same port, each as an optional extra so
a CLI user carries no HTTP client they never run (CON-59, D-003's discipline).
"""

from .git_pages import NAME, GitPages, detect, wiki_url

__all__ = ["NAME", "GitPages", "detect", "wiki_url"]
