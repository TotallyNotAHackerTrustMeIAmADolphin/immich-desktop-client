"""Guard for ADR 0001: the client never force-deletes and has exactly one place that sends a DELETE.

Behavioural half: every delete flow may only send DELETE /assets with a body of exactly {"ids": [...]}.
Static half: src/ contains one DELETE call site, no requests.delete, and no "force" string literal.
If one of these fails, do not loosen the test; re-read docs/adr/0001-never-force-delete.md.
"""
import ast
import pathlib

import immich
from test_upload import make_photo

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"


# ---- behavioural: whatever flow trashes, the request is trash-only ------------------------------------------

def assert_trash_only(api):
    assert api.delete_requests, "the flow under test never sent a DELETE"
    for url, params, body in api.delete_requests:
        assert url == "http://immich.test/api/assets"
        assert not params  # no ?force=true style query
        assert set(body) == {"ids"}  # no force key (or any other key), ever
        assert body["ids"] and all(isinstance(i, str) for i in body["ids"])


def test_live_delete_sends_only_ids(deleting_client, api, tmp_path):
    photo = make_photo(tmp_path)
    deleting_client.created(str(photo))
    deleting_client.delete(str(photo))
    assert_trash_only(api)


def test_delete_all_sends_only_ids(client, api, tmp_path):
    client.created(str(make_photo(tmp_path)))
    client.delete_all_own_uploads()
    assert_trash_only(api)


def test_replace_sends_only_ids(client, api, tmp_path):
    photo = make_photo(tmp_path)
    client.created(str(photo))
    photo.write_bytes(b"v2")
    client.modify(str(photo))
    assert_trash_only(api)


def test_catch_up_delete_sends_only_ids(api, tmp_path):
    client = immich.Immich("http://immich.test/api", "key", album_name="t", album_id="a",
                           record_path=str(tmp_path / "r.sqlite"), catch_up_delete=True)
    root = tmp_path / "pics"
    root.mkdir()
    client.upload_all_images([str(root)], (".jpg",))
    photo = make_photo(root, "a.jpg")
    client.created(str(photo))
    photo.unlink()
    make_photo(root, "other.jpg")
    client.upload_all_images([str(root)], (".jpg",))
    assert_trash_only(api)


# ---- static: one DELETE call site, no force vocabulary -------------------------------------------------------

def source_trees():
    return {path: ast.parse(path.read_text(encoding="utf-8")) for path in sorted(SRC.glob("*.py"))}


def docstring_nodes(tree):
    nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                nodes.add(first.value)
    return nodes


def test_exactly_one_delete_call_site_exists_in_src():
    sites = [(path.name, node.lineno)
             for path, tree in source_trees().items()
             for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip() == "DELETE"]
    assert len(sites) == 1, f"expected the single trash call site, found {sites}"
    assert sites[0][0] == "immich.py"


def test_no_http_delete_shortcut_is_used():
    offenders = [(path.name, node.lineno)
                 for path, tree in source_trees().items()
                 for node in ast.walk(tree)
                 if isinstance(node, ast.Attribute) and node.attr == "delete"
                 and isinstance(node.value, ast.Name) and node.value.id in {"requests", "session", "httpx", "urllib3"}]
    assert offenders == []


def test_no_force_string_literal_in_src():
    offenders = []
    for path, tree in source_trees().items():
        skip = docstring_nodes(tree)
        offenders += [(path.name, node.lineno)
                      for node in ast.walk(tree)
                      if isinstance(node, ast.Constant) and isinstance(node.value, str)
                      and node not in skip and "force" in node.value.lower()]
    assert offenders == []
