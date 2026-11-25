# -*- coding: utf-8 -*-
"""登录、角色与口令。口令存 sha256，演示账号见 README。"""
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


def change_password(conn, username: str, old: str, new: str) -> None:
    """改自己的口令。旧口令不对、新口令太短都直接抛 ValueError，页面照原样显示。"""
    row = conn.execute(
        "SELECT pwd_hash FROM app_user WHERE username=?", (username,)).fetchone()
    if row is None:
        raise ValueError("没有这个账号")
    if row["pwd_hash"] != hash_pwd(old):
        raise ValueError("原密码不对")
    if len(new) < 6:
        raise ValueError("新密码至少 6 位")
    if hash_pwd(new) == row["pwd_hash"]:
        raise ValueError("新密码和原密码一样")
    conn.execute("UPDATE app_user SET pwd_hash=? WHERE username=?",
                 (hash_pwd(new), username))
    conn.commit()


def reset_password(conn, username: str, new: str) -> None:
    """店主给店员重置口令，不需要店员的旧口令。"""
    if len(new) < 6:
        raise ValueError("新密码至少 6 位")
    if conn.execute("SELECT 1 FROM app_user WHERE username=?", (username,)).fetchone() is None:
        raise ValueError("没有这个账号")
    conn.execute("UPDATE app_user SET pwd_hash=? WHERE username=?",
                 (hash_pwd(new), username))
    conn.commit()


def can_see_cost(role: str) -> bool:
    return role == "owner"
