#!/usr/bin/env python3
"""Push portal-main v3.2 to ori-yin/ideon-portal via Git Data API.

github.com 被墙，走 api.github.com。
4 步：blobs → trees → commits → PATCH ref
"""
import os, sys, json, base64, subprocess, urllib.request, urllib.error, time

TOKEN = os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    sys.exit("GITHUB_TOKEN env var required (e.g. $env:GITHUB_TOKEN='ghp_...')")
REPO = "ori-yin/ideon-portal"
BRANCH = "main"
# 每次 push 前用 `curl -H "Authorization: token ..." https://api.github.com/repos/ori-yin/ideon-portal/git/ref/heads/main` 拿 HEAD
REMOTE_HEAD_SHA = "14c216328bfe6c7173e77b8b608e76f1a0c4711b"
REMOTE_TREE_SHA = "6821f3ef59367895b4f9c7a14133b93773d5489a"
REPO_DIR = r"C:\ideon\ideon-portal-main"

API = "https://api.github.com"


def http(method, path, body=None, retried=False):
    url = f"{API}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
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


def main():
    # 1. 列出本地所有 tracked files（core.quotePath=false 避免中文转义）
    # git ls-tree 输出是 UTF-8（即使磁盘文件名是 GBK 字节）
    files_raw = subprocess.check_output(
        ["git", "-C", REPO_DIR, "-c", "core.quotePath=false", "ls-tree", "-r", "--name-only", "HEAD"],
    )
    files = files_raw.decode("utf-8", errors="replace").splitlines()
    print(f"local files: {len(files)}")

    # 2. 拉远端 tree，找要删的
    remote_tree = http("GET", f"/repos/{REPO}/git/trees/{REMOTE_TREE_SHA}?recursive=1")
    remote_paths = {t["path"] for t in remote_tree["tree"] if t["type"] == "blob"}
    local_paths = set(files)
    to_delete = sorted(remote_paths - local_paths)
    print(f"remote blobs: {len(remote_paths)}, to_delete: {len(to_delete)}")
    for p in to_delete:
        print(f"  DEL {p}")

    # 3. POST blobs（所有本地文件）
    print("\n--- Step 1: POST blobs ---")
    tree_entries = []
    for i, relpath in enumerate(files, 1):
        # Windows 磁盘文件名可能是 GBK 字节，unicode 路径要先 encode 回 cp 再 open
        # 简单粗暴：open with surrogateescape 拿到 bytes 路径
        try:
            full_bytes = os.fsencode(os.path.join(REPO_DIR, relpath))
            with open(full_bytes, "rb") as f:
                content_bytes = f.read()
        except OSError:
            # fallback: 用 git cat-file（避开编码问题）
            ls_out = subprocess.check_output(
                ["git", "-C", REPO_DIR, "-c", "core.quotePath=false", "ls-tree", "-r", "HEAD"],
                text=True, encoding="utf-8"
            )
            local_sha = None
            for ln in ls_out.splitlines():
                parts = ln.split(None, 3)
                if len(parts) >= 4 and parts[3] == relpath:
                    local_sha = parts[2]
                    break
            if not local_sha:
                print(f"  WARN no sha for {relpath!r}, skip")
                continue
            content_bytes = subprocess.check_output(
                ["git", "-C", REPO_DIR, "cat-file", "blob", local_sha]
            )
        # 二进制检测：尝试 utf-8 解码
        try:
            content_bytes.decode("utf-8")
            content_str = content_bytes.decode("utf-8")
            blob_body = {"content": content_str, "encoding": "utf-8"}
        except UnicodeDecodeError:
            content_b64 = base64.b64encode(content_bytes).decode("ascii")
            blob_body = {"content": content_b64, "encoding": "base64"}

        result = http("POST", f"/repos/{REPO}/git/blobs", blob_body)
        blob_sha = result["sha"]
        tree_entries.append({
            "path": relpath,
            "mode": "100644",
            "type": "blob",
            "sha": blob_sha
        })
        if i % 20 == 0 or i == len(files):
            print(f"  [{i}/{len(files)}] blobs uploaded")

    # 4. 删文件（sha: null）
    for relpath in to_delete:
        tree_entries.append({
            "path": relpath,
            "mode": "100644",
            "type": "blob",
            "sha": None
        })

    # 5. POST trees
    print("\n--- Step 2: POST trees ---")
    tree_body = {"base_tree": REMOTE_TREE_SHA, "tree": tree_entries}
    new_tree = http("POST", f"/repos/{REPO}/git/trees", tree_body)
    new_tree_sha = new_tree["sha"]
    print(f"new tree sha: {new_tree_sha}")

    # 6. POST commits
    print("\n--- Step 3: POST commits ---")
    commit_msg = """init: v3.2 整合 + LLM 配置

- 整合 portal-clone 苹果风首页（37.3KB，覆盖 main 旧 v3 中性版）
- 移植 LLM 配置 modal（HTMX + 自包含 style），保存到 ~/.ideon-portal/llm_settings.yaml
- 新增 /api/settings/llm-modal|llm|llm/test 三个路由
- topbar LLM pill 改为可点击（点开配置弹窗）
- HANDOFF.md 增加 v3.2 章节
- 增加 .gitignore（_bak-* / *.db / __pycache__ 等不进 git）
- 删 dev-handoff-v2.md（旧版交接文档）
"""
    commit_body = {
        "message": commit_msg,
        "tree": new_tree_sha,
        "parents": [REMOTE_HEAD_SHA]
    }
    new_commit = http("POST", f"/repos/{REPO}/git/commits", commit_body)
    new_commit_sha = new_commit["sha"]
    print(f"new commit sha: {new_commit_sha}")

    # 7. PATCH ref
    print("\n--- Step 4: PATCH ref ---")
    http("PATCH", f"/repos/{REPO}/git/refs/heads/{BRANCH}", {"sha": new_commit_sha})
    print(f"main -> {new_commit_sha}")

    print("\nDONE. Verify:")
    verify = http("GET", f"/repos/{REPO}/git/ref/heads/{BRANCH}")
    print(f"  remote HEAD now: {verify['object']['sha']}")
    if verify["object"]["sha"] == new_commit_sha:
        print("  OK")
    else:
        print("  MISMATCH!")


if __name__ == "__main__":
    main()
