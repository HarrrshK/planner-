import curses
import sqlite3
from datetime import date, datetime, timedelta
from dateutil import parser as date_parser

DB_FILE = "todos.db"


# ---------- DB Setup ----------
def init_db():
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY,
            title TEXT,
            category TEXT,
            due TEXT,
            done INTEGER DEFAULT 0,
            deleted INTEGER DEFAULT 0
        )"""
    )
    con.commit()
    return con


# ---------- Date Parsing ----------
def parse_due_date(s: str) -> str:
    s = s.strip().lower()
    if not s:
        return ""
    today = date.today()
    if s == "today":
        return today.isoformat()
    if s == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    if s.startswith("+") and s.endswith("d") and s[1:-1].isdigit():
        return (today + timedelta(days=int(s[1:-1]))).isoformat()
    if s.startswith("+") and s.endswith("w") and s[1:-1].isdigit():
        return (today + timedelta(weeks=int(s[1:-1]))).isoformat()
    try:
        return date_parser.parse(s).date().isoformat()
    except:
        return s


# ---------- DB Operations ----------
def add_todo(con, title, category, due):
    cur = con.cursor()
    cur.execute(
        "INSERT INTO todos(title, category, due, done, deleted) VALUES (?,?,?,?,0)",
        (title, category, parse_due_date(due), 0),
    )
    con.commit()


def mark_done(con, tid):
    cur = con.cursor()
    cur.execute("UPDATE todos SET done=1 WHERE id=?", (tid,))
    con.commit()


def delete_todo(con, tid):
    cur = con.cursor()
    cur.execute("UPDATE todos SET deleted=1 WHERE id=?", (tid,))
    con.commit()


def get_stats(con, where_clause="", params=()):
    cur = con.cursor()
    total = cur.execute(
        f"SELECT COUNT(*) FROM todos WHERE deleted=0 {where_clause}", params
    ).fetchone()[0]
    done = cur.execute(
        f"SELECT COUNT(*) FROM todos WHERE done=1 AND deleted=0 {where_clause}",
        params,
    ).fetchone()[0]
    return total, done


# ---------- UI Helpers ----------
def draw_progress_bar(win, y, x, percent, width):
    filled = int((percent / 100) * width)
    bar = "[" + "#" * filled + "-" * (width - filled) + f"] {percent}%"
    win.addstr(y, x, bar)


def draw_dashboard(stdscr, con, cursor_idx, where_clause="", params=(), subtitle=""):
    stdscr.clear()
    stdscr.addstr(0, 0, "📋 Daily Planner (Dashboard)")
    stdscr.addstr(1, 0, "a=add  d=done  x=delete  c=completed  /=search  f=filter  q=quit")
    stdscr.addstr(2, 0, "-" * 50)

    if subtitle:
        stdscr.addstr(3, 0, subtitle, curses.A_BOLD)

    cur = con.cursor()
    cur.execute(
        f"SELECT id, title, category, due, done FROM todos WHERE deleted=0 AND done=0 {where_clause} ORDER BY id DESC",
        params,
    )
    todos = cur.fetchall()

    if not todos:
        stdscr.addstr(5, 0, "No todos yet!", curses.A_DIM)
    else:
        for idx, t in enumerate(todos):
            tid, title, cat, due_str, done = t
            prefix = "[x] " if done else "[ ] "

            attr = 0
            if due_str and not done:
                try:
                    d = datetime.strptime(due_str, "%Y-%m-%d").date()
                    if d < date.today():
                        attr = curses.color_pair(1)
                    elif d == date.today():
                        attr = curses.color_pair(2)
                    else:
                        attr = curses.color_pair(3)
                except:
                    pass

            marker = "-> " if idx == cursor_idx else "   "
            stdscr.addstr(5 + idx, 0, marker)
            stdscr.addstr(f"{prefix}{title} ", attr)
            if cat:
                stdscr.addstr(f"#{cat}", curses.color_pair(4))
            if due_str:
                stdscr.addstr(f" (due {due_str})", attr)

    total, done = get_stats(con, where_clause, params)
    progress = int((done / total) * 100) if total else 0
    stdscr.addstr(18, 0, f"Total: {total}  Done: {done}  Progress: {progress}%")
    draw_progress_bar(stdscr, 19, 0, progress, stdscr.getmaxyx()[1] - 7)

    stdscr.refresh()
    return todos


def draw_completed(stdscr, con):
    stdscr.clear()
    stdscr.addstr(0, 0, "✅ Completed Todos (press b to go back)")
    stdscr.addstr(1, 0, "-" * 50)

    cur = con.cursor()
    cur.execute(
        "SELECT id, title, category, due FROM todos WHERE deleted=0 AND done=1 ORDER BY id DESC"
    )
    todos = cur.fetchall()

    if not todos:
        stdscr.addstr(3, 0, "No completed todos yet!", curses.A_DIM)
    else:
        for idx, t in enumerate(todos):
            tid, title, cat, due_str = t
            stdscr.addstr(3 + idx, 0, f"[x] {title} ")
            if cat:
                stdscr.addstr(f"#{cat}", curses.color_pair(4))
            if due_str:
                stdscr.addstr(f" (due {due_str})")

    stdscr.refresh()


# ---------- Main Loop ----------
def main(stdscr):
    con = init_db()
    curses.curs_set(0)
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)  # overdue
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # today
    curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)  # future
    curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)  # category

    view = "dashboard"
    cursor_idx = 0
    where_clause = ""
    params = ()
    subtitle = ""

    while True:
        todos = []

        if view == "dashboard":
            todos = draw_dashboard(stdscr, con, cursor_idx, where_clause, params, subtitle)
        elif view == "completed":
            draw_completed(stdscr, con)

        ch = stdscr.getch()

        if ch == ord("q"):
            break
        elif view == "dashboard":
            if ch == curses.KEY_UP and todos:
                cursor_idx = (cursor_idx - 1) % len(todos)
            elif ch == curses.KEY_DOWN and todos:
                cursor_idx = (cursor_idx + 1) % len(todos)
            elif ch == ord("a"):
                curses.echo()
                stdscr.clear()
                stdscr.addstr(0, 0, "Title: ")
                title = stdscr.getstr().decode("utf-8")
                stdscr.addstr(1, 0, "Category: ")
                category = stdscr.getstr().decode("utf-8")
                stdscr.addstr(2, 0, "Due (YYYY-MM-DD, today, tomorrow, +3d): ")
                due = stdscr.getstr().decode("utf-8")
                curses.noecho()
                add_todo(con, title, category, due)
                cursor_idx = 0
                where_clause, params, subtitle = "", (), ""
            elif ch == ord("d") and todos:
                mark_done(con, todos[cursor_idx][0])
                cursor_idx = 0
            elif ch == ord("x") and todos:
                delete_todo(con, todos[cursor_idx][0])
                cursor_idx = 0
            elif ch == ord("c"):
                view = "completed"
            elif ch == ord("f"):  # filter by category
                curses.echo()
                stdscr.addstr(21, 0, "Filter by category (#tag): ")
                cat = stdscr.getstr().decode("utf-8")
                curses.noecho()
                if cat:
                    where_clause, params = "AND category=?", (cat,)
                    subtitle = f"Filtered by #{cat}"
                    cursor_idx = 0
            elif ch == ord("/"):  # search by keyword
                curses.echo()
                stdscr.addstr(21, 0, "Search title: ")
                query = stdscr.getstr().decode("utf-8")
                curses.noecho()
                if query:
                    where_clause, params = "AND title LIKE ?", (f"%{query}%",)
                    subtitle = f"Search results for '{query}'"
                    cursor_idx = 0
            elif ch == ord("b"):  # back to full list
                where_clause, params, subtitle = "", (), ""
                cursor_idx = 0
        elif view == "completed":
            if ch == ord("b"):
                view = "dashboard"
                cursor_idx = 0


if __name__ == "__main__":
    curses.wrapper(main)
