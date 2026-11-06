"""Guard for ADR 0001: the client never force-deletes and has exactly one place that sends a DELETE.

Behavioural half: every delete flow may only send DELETE /assets with a body of exactly {"ids": [...]}.
Static half: src/ contains one DELETE call site, no requests.delete, and no "force" string literal.

Known limit of the static half: it cannot prove a method name is not computed at runtime inside the one forwarding
function (__request); the behavioural half and the fake server (which rejects any DELETE that is not exactly
/assets with {"ids"}) cover that. Code run through eval/exec or C extensions is out of scope.
If one of these fails, do not loosen the test; re-read docs/adr/0001-never-force-delete.md.
"""
import ast
import pathlib
import re

import pytest

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
    assert len(sites) == 1, f"ADR 0001: expected exactly one \"DELETE\" literal (in Immich.__trash), found {sites}"
    assert sites[0][0] == "immich.py"


# Receivers of `.delete(...)` that exist in src today and are not HTTP (registry key, tk listboxes, our own wrapper).
ALLOWED_DELETE_RECEIVERS = {
    ("autostart.py", "run_key"),
    ("main.py", "api"),
    ("progress_window.py", "failures"),
    ("settings_dialog.py", "folders"),
}


def test_only_known_non_http_delete_methods_are_called():
    offenders = [(path.name, node.lineno, ast.unparse(node.func.value))
                 for path, tree in source_trees().items()
                 for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "delete"
                 and (path.name, ast.unparse(node.func.value)) not in ALLOWED_DELETE_RECEIVERS]
    assert offenders == [], "unknown .delete() receiver: if it is not HTTP, add (file, receiver) to ALLOWED_DELETE_RECEIVERS; otherwise it is a second DELETE path (ADR 0001): " + repr(offenders)


def test_requests_is_only_imported_by_immich_py():
    offenders = []
    for path, tree in source_trees().items():
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
                if path.name == "immich.py" and any(a.asname for a in node.names if a.name == "requests"):
                    offenders.append((path.name, node.lineno, "aliased import"))
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            if any(m.split(".")[0] in {"requests", "urllib3", "httpx", "http", "urllib"} for m in mods):
                if path.name != "immich.py" or isinstance(node, ast.ImportFrom) or mods != ["requests"]:
                    offenders.append((path.name, node.lineno, mods))
            # dynamic import by name: __import__("requests"), importlib.import_module("requests")
            if isinstance(node, ast.Constant) and node.value in {"requests", "urllib3", "httpx"}:
                offenders.append((path.name, node.lineno, "string " + node.value))
    assert offenders == [], "requests/urllib3/httpx may only be imported as plain `import requests` by immich.py (one HTTP module, one DELETE site, ADR 0001); move the HTTP call into immich.py: " + repr(offenders)


def test_immich_py_only_uses_known_requests_entry_points():
    tree = source_trees()[SRC / "immich.py"]
    offenders = [node.lineno for node in ast.walk(tree)
                 if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "requests"
                 and node.attr not in {"request", "post", "exceptions"}]
    assert offenders == [], "immich.py may only use requests.request/post/exceptions; extend the list in this test after a review of the new entry point: " + repr(offenders)


# Exactly the HTTP methods immich.py sends today. requests uppercases whatever it is given, so a literal such as
# "delete" or "Delete" would be a real DELETE; only exact uppercase members are accepted.
ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE"}


def method_problems(tree):
    """Problems with the HTTP method of every requests.request / __request call in a parsed module."""
    problems = []

    def visit(node, function):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function = node.name
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            target = node.func
            is_requests_request = (target.attr == "request" and isinstance(target.value, ast.Name)
                                   and target.value.id == "requests")
            is_wrapper = target.attr in {"__request", "_Immich__request"}
            if is_requests_request or is_wrapper:
                first = node.args[0] if node.args else None
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    if first.value not in ALLOWED_METHODS:
                        problems.append((node.lineno, f"method literal {first.value!r} is not one of "
                                         f"{sorted(ALLOWED_METHODS)}: method literals must be uppercase "
                                         "(requests uppercases them); a new method needs ALLOWED_METHODS and a review"))
                    elif first.value == "DELETE" and function != "__trash":
                        problems.append((node.lineno, "DELETE is only allowed inside __trash (ADR 0001)"))
                elif not (is_requests_request and function == "__request"
                          and isinstance(first, ast.Name) and first.id == "method"):
                    problems.append((node.lineno, "the HTTP method must be a string literal (only __request may "
                                     "forward its own 'method' parameter): " + ast.unparse(node)[:60]))
        for child in ast.iter_child_nodes(node):
            visit(child, function)

    visit(tree, None)
    return problems


def test_every_request_call_passes_an_allowed_uppercase_literal_method():
    """Closes "DEL"+"ETE", "delete".upper(), "delete"/"Delete"/"DELETE " and variable methods.

    Known limit: a method computed at runtime inside __request cannot be proven statically; the fake server and
    the behavioural tests cover it. getattr(<other name>, "de"+"lete") on an alias is caught only because
    the module name `requests` may not be used bare (see test_requests_module_is_never_used_as_a_value).
    """
    assert method_problems(source_trees()[SRC / "immich.py"]) == []


@pytest.mark.parametrize("literal", ["delete", "Delete", "DELETE ", "get", "Get", "PATCH"])
@pytest.mark.parametrize("call", ['requests.request({m!r}, url)', 'self.__request({m!r}, "/assets")'])
def test_method_checker_rejects_bad_literals(call, literal):
    tree = ast.parse("def f(self, url):\n    return " + call.format(m=literal))
    assert method_problems(tree), f"{literal!r} should have been rejected"


@pytest.mark.parametrize("source", [
    "def f(self, url):\n    return requests.request('GET', url)",
    "def __trash(self, ids):\n    return self.__request('DELETE', '/assets')",
    "def __request(self, method, path):\n    return requests.request(method, path)",
])
def test_method_checker_accepts_known_good_calls(source):
    assert method_problems(ast.parse(source)) == []


def test_method_checker_rejects_delete_outside_trash():
    assert method_problems(ast.parse("def other(self):\n    return self.__request('DELETE', '/assets')"))


def test_requests_module_is_never_used_as_a_value():
    """Bans getattr(requests, "delete"), x = requests, setattr/vars(requests): `requests` may only be followed by
    an attribute access (checked against an entry-point list above)."""
    offenders = []
    for path, tree in source_trees().items():
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "requests" and isinstance(node.ctx, ast.Load):
                parent = parents.get(node)
                if not (isinstance(parent, ast.Attribute) and parent.value is node):
                    offenders.append((path.name, node.lineno,
                                      "use requests.<name> directly; do not pass or alias the module (ADR 0001)"))
    assert offenders == []

# ---- the fake server enforces the same rule, so a bad DELETE fails any test that causes it -------------------

@pytest.mark.parametrize("params, body", [
    (None, {"ids": ["a"], "force": True}),
    ({"force": "true"}, {"ids": ["a"]}),
    (None, {"force": True}),
    (None, None),
])
def test_fake_server_rejects_a_non_trash_delete(api, params, body):
    import json
    data = json.dumps(body) if body is not None else None
    with pytest.raises(AssertionError, match="ADR 0001"):
        api.request("DELETE", "http://immich.test/api/assets", data=data, params=params)


def test_fake_server_rejects_delete_of_another_path(api):
    with pytest.raises(AssertionError, match="ADR 0001"):
        api.request("DELETE", "http://immich.test/api/albums/x", data='{"ids": ["a"]}')


def test_fake_server_accepts_a_trash_delete(api):
    api.request("DELETE", "http://immich.test/api/assets", data='{"ids": ["a"]}')
    assert api.deletes == [{"ids": ["a"]}]


# ---- no force vocabulary --------------------------------------------------------------------------------------

# "force" as a word or camelCase part; not inside enforce/forced/reinforced
FORCE = re.compile(r"(?:(?<![A-Za-z])[Ff]|(?<=[a-z])F)[Oo][Rr][Cc][Ee](?![a-z])")


@pytest.mark.parametrize("text, flagged", [
    ("force", True), ("Force", True), ("FORCE", True), ("force_rescan", True), ("forceDelete", True), ("isForce", True),
    ("?force=true", True), ("enforce", False), ("forced", False), ("reinforced", False), ("Enforcement", False),
])
def test_force_matcher(text, flagged):
    assert bool(FORCE.search(text)) is flagged


def test_no_force_string_literal_in_src():
    offenders = []
    for path, tree in source_trees().items():
        skip = docstring_nodes(tree)
        offenders += [(path.name, node.lineno)
                      for node in ast.walk(tree)
                      if isinstance(node, ast.Constant) and isinstance(node.value, str)
                      and node not in skip and FORCE.search(node.value)]
    assert offenders == [], "a string literal contains the word force (ADR 0001: the client never force-deletes); rename it or, if it is unrelated, review and narrow FORCE: " + repr(offenders)
