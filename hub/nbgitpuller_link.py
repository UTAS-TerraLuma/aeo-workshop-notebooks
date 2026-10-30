"""
nbgitpuller_link.py
===================
Print the nbgitpuller links to hand out to attendees. Clicking one logs the
attendee in, copies (or updates) the workshop repo into their home folder and
opens it in JupyterLab. Re-clicking later pulls new commits without
overwriting their own edits.

The repo must be on a public git host first (e.g. GitHub).

    python hub/nbgitpuller_link.py https://aeo-hub.myproject.cloud.edu.au \
        https://github.com/UTAS-TerraLuma/aeo-workshop-notebooks

Only uses the standard library, so any Python 3 works.
"""

import argparse
from urllib.parse import urlencode

CHAPTERS = [
    "CHAPTER1_DATA_and_VISUALISATION.ipynb",
    "CHAPTER2_COMPUTING_VISUALISING_DERIVATIVES_FINAL.ipynb",
    "CHAPTER3_QA_MASKING.ipynb",
    "CHAPTER4_OPTIONAL_PROXY_DERIVATIVES.ipynb",
]


def make_link(hub, repo, branch, path=""):
    """nbgitpuller link that opens `path` (inside the repo folder) in JupyterLab."""
    folder = repo.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1]
    target = f"{folder}/{path}" if path else folder
    query = urlencode({
        "repo": repo,
        "branch": branch,
        "urlpath": f"lab/tree/{target}",
    })
    return f"{hub.rstrip('/')}/hub/user-redirect/git-pull?{query}"


parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
parser.add_argument("hub", help="hub address, e.g. https://aeo-hub.myproject.cloud.edu.au")
parser.add_argument("repo", help="public git URL of the workshop repo")
parser.add_argument("--branch", default="main")
args = parser.parse_args()

print("Workshop folder (hand this one out):")
print(" ", make_link(args.hub, args.repo, args.branch))
for chapter in CHAPTERS:
    print(f"\n{chapter}:")
    print(" ", make_link(args.hub, args.repo, args.branch, chapter))
