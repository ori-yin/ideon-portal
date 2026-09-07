#!/usr/bin/env python3
"""Push portal-main to ori-yin/ideon-portal via Git Data API.

github.com 被墙，走 api.github.com。

模式：顺序推保留历史（v2）
- 动态拿远端 HEAD（不再写死 REMOTE_HEAD_SHA）
- 用 git rev-list 找本地未推 commit（oldest first）
- 对每条 commit：POST blobs（基于该 commit 的 tree）→ POST trees → POST commits → PATCH ref
- 父链用远端当前的 HEAD（不是本地 parent），保证每条 commit 都挂到远端 chain 上

Token 走环境变量 GITHUB_TOKEN（不能写死，secret scanning 拦）：
  $env:GITHUB_TOKEN = "ghp_..."; python tools/push_via_api.py
"""
import os
import sys
import json
import base64
import subprocess
import time
import urllib.request
import urllib.error

TOKEN = os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    sys.exit("GITHUB_TOKEN env var required (e.g. $env:GITHUB_TOKEN='ghp_...')")
REPO = "ori-yin/ideon-portal"
BRANCH = "main"
REPO_DIR = r"C:\ideon\ideon-portal-main"
API = "https://api.github.com"


def git(*args):
    return subprocess.check_output(
        ["git", "-C", REPO_DIR, *args],
        text=True, encoding="utf-8", errors="replace",
    )


def http(method, path, body=None, retried=False):
    url = f"{API}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        # 422 BadObjectState: parent tree 还没 indexed → 等 3 秒重试一次
        if e.code == 422 and "BadObjectState" in body_text and not retried:
            print(f"  422 BadObjectState, retry in 3s...")
            time.sleep(3)
            return http(method, path, body, retried=True)
        print(f"HTTP {e.code} {method} {path}")
        print(body_text[:500])
        raise


def get_remote_head():
    return http("GET", f"/repos/{REPO}/git/ref/heads/{BRANCH}")["object"]["sha"]


def get_remote_tree(remote_head_sha):
    """通过 API 取远端 HEAD commit 的 tree SHA。"""
    commit = http("GET", f"/repos/{REPO}/git/commits/{remote_head_sha}")
    return commit["tree"]["sha"]


def get_local_head():
    return git("rev-parse", "HEAD").strip()


def get_commit_tree(sha):
    raw = git("cat-file", "-p", sha)
    for line in raw.split("\n"):
        if line.startswith("tree "):
            return line.split()[1]
    return None


def get_commit_parent(sha):
    raw = git("cat-file", "-p", sha)
    for line in raw.split("\n"):
        if line.startswith("parent "):
            return line.split()[1]
    return None


def get_unpushed_commits():
    """从本地 HEAD 沿 parent chain 向上走，收集「message 不在远端最近 20 个 commit」的 commit（oldest first）。

    不依赖 tree SHA 比较（GitHub blob/tree SHA 算法跟本地 git 不同，相同内容 SHA 也不同）。
    用 commit message 作为内容指纹——message 字符串在跨环境传输时不会变。
    不依赖 git fetch / rev-list（github.com 被墙）。
    """
    # 拿远端最近 20 个 commit 的 message
    remote_commits = http("GET", f"/repos/{REPO}/commits?sha={BRANCH}&per_page=20")
    remote_messages = {c["commit"]["message"].strip() for c in remote_commits}

    unpushed = []
    current = get_local_head()
    while current:
        info = get_commit_info(current)
        msg = info["message"].strip()
        if msg in remote_messages:
            break  # 这个 commit 已经推过（message 指纹匹配）
        unpushed.append(current)
        parent = get_commit_parent(current)
        if not parent:
            break  # 到 root
        current = parent
    return list(reversed(unpushed))


def get_commit_info(sha):
    """解析 git cat-file -p <sha>，返回 {tree, message}。"""
    raw = git("cat-file", "-p", sha)
    tree = None
    lines = raw.split("\n")
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("tree "):
            tree = l.split()[1]
        elif l.strip() == "":
            i += 1
            break
        i += 1
    message = "\n".join(lines[i:]).rstrip("\n")
    return {"tree": tree, "message": message}


def get_tree_files(tree_sha):
    """返回 [(path, blob_sha), ...] 列表。"""
    out = git("ls-tree", "-r", tree_sha)
    files = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 4 and parts[1] == "blob":
            files.append((parts[3], parts[2]))
    return files


def upload_blob(local_sha):
    """从本地 git 对象读 blob 内容，上传。"""
    raw = subprocess.check_output(
        ["git", "-C", REPO_DIR, "cat-file", "blob", local_sha],
    )
    try:
        text = raw.decode("utf-8")
        return http("POST", f"/repos/{REPO}/git/blobs",
                    {"content": text, "encoding": "utf-8"})["sha"]
    except UnicodeDecodeError:
        b64 = base64.b64encode(raw).decode("ascii")
        return http("POST", f"/repos/{REPO}/git/blobs",
                    {"content": b64, "encoding": "base64"})["sha"]


def upload_tree(files, blob_shas):
    entries = [{"path": p, "mode": "100644", "type": "blob", "sha": blob_shas[p]}
               for p, _ in files]
    return http("POST", f"/repos/{REPO}/git/trees", {"tree": entries})["sha"]


def main():
    print("=== portal push_via_api v2 (sequential) ===\n")
    local_head = get_local_head()
    remote_head = get_remote_head()
    print(f"local HEAD : {local_head}")
    print(f"remote HEAD: {remote_head}")

    # 通过 API 比对 commit message 找未推 commit（github.com 被墙不走 git fetch）
    unpushed = get_unpushed_commits()
    if not unpushed:
        print("\nNo unpushed commits (all local commits' trees match remote). Done.")
        return
    print(f"\nunpushed commits: {len(unpushed)}")
    for s in unpushed:
        msg = get_commit_info(s)["message"].splitlines()[0]
        print(f"  {s[:10]}  {msg}")

    current_remote = remote_head
    for idx, sha in enumerate(unpushed, 1):
        info = get_commit_info(sha)
        title = info["message"].splitlines()[0]
        files = get_tree_files(info["tree"])
        print(f"\n[{idx}/{len(unpushed)}] {sha[:10]}  {title}")
        print(f"  tree={info['tree'][:10]}  files={len(files)}")

        # 1. POST blobs
        blob_shas = {}
        for i, (path, local_blob_sha) in enumerate(files, 1):
            blob_shas[path] = upload_blob(local_blob_sha)
        print(f"  blobs: {len(blob_shas)} uploaded")

        # 2. POST trees
        new_tree_sha = upload_tree(files, blob_shas)
        print(f"  tree  : {new_tree_sha}")

        # 3. POST commit (parent = 当前远端 HEAD，保持 chain)
        new_commit_sha = http(
            "POST", f"/repos/{REPO}/git/commits",
            {"message": info["message"], "tree": new_tree_sha, "parents": [current_remote]},
        )["sha"]
        print(f"  commit: {new_commit_sha}")

        # 4. PATCH ref
        http("PATCH", f"/repos/{REPO}/git/refs/heads/{BRANCH}",
             {"sha": new_commit_sha})
        print(f"  ref   : main -> {new_commit_sha[:10]}")
        current_remote = new_commit_sha

    print(f"\n=== DONE ===")
    verify = http("GET", f"/repos/{REPO}/git/ref/heads/{BRANCH}")
    if verify["object"]["sha"] == current_remote:
        print(f"remote HEAD = {verify['object']['sha']}  OK")
    else:
        print(f"MISMATCH! remote={verify['object']['sha']} expected={current_remote}")


if __name__ == "__main__":
    main()
