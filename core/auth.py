# -*- coding: utf-8 -*-
"""登录与角色。密码存 sha256，演示账号见 README。"""
import hashlib


def hash_pwd(p: str) -> str:
    return hashlib.sha256(p.encode("utf-8")).hexdigest()


def check(conn, username: str, password: str):
    row = conn.execute(
        "SELECT username, pwd_hash, role FROM app_user WHERE username=?", (username,)
    ).fetchone()
    if row and row["pwd_hash"] == hash_pwd(password):
        return dict(username=row["username"], role=row["role"])
    return None


def can_see_cost(role: str) -> bool:
    return role == "owner"
