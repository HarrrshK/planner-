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
            priority TEXT DEFAULT 'Medium',
            done INTEGER DEFAULT 0,
            deleted INTEGER DEFAULT 0,
            completed_date TEXT
        )"""
    )
    # Add columns to existing tables
    try:
        cur.execute("ALTER TABLE todos ADD COLUMN priority TEXT DEFAULT 'Medium'")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE todos ADD COLUMN completed_date TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Settings table for daily goal
    cur.execute(
        """CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )"""
    )
    # Set default daily goal if not exists
    cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES ('daily_goal', '5')")
    
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
def add_todo(con, title, category, due, priority):
    cur = con.cursor()
    cur.execute(
        "INSERT INTO todos(title, category, due, priority, done, deleted) VALUES (?,?,?,?,0,0)",
        (title, category, parse_due_date(due), priority),
    )
    con.commit()


def mark_done(con, tid):
    cur = con.cursor()
    today = date.today().isoformat()
    cur.execute("UPDATE todos SET done=1, completed_date=? WHERE id=?", (today, tid))
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


def get_daily_goal(con):
    cur = con.cursor()
    result = cur.execute("SELECT value FROM settings WHERE key='daily_goal'").fetchone()
    return int(result[0]) if result else 5


def set_daily_goal(con, goal):
    cur = con.cursor()
    cur.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('daily_goal', ?)", (str(goal),))
    con.commit()


def get_today_completed(con):
    cur = con.cursor()
    today = date.today().isoformat()
    count = cur.execute(
        "SELECT COUNT(*) FROM todos WHERE deleted=0 AND done=1 AND completed_date=?",
        (today,)
    ).fetchone()[0]
    return count


# ---------- UI Helpers ----------
def draw_progress_bar(win, y, x, percent, width):
    filled = int((percent / 100) * width)
    bar = "[" + "#" * filled + "-" * (width - filled) + f"] {percent}%"
    win.addstr(y, x, bar)


def get_priority_order(priority):
    """Return sort order for priority (lower is higher priority)"""
    order = {"High": 0, "Medium": 1, "Low": 2}
    return order.get(priority, 1)


def draw_dashboard(stdscr, con, cursor_idx, where_clause="", params=(), subtitle=""):
    stdscr.clear()
    stdscr.addstr(0, 0, "📋 Daily Planner (Dashboard)")
    stdscr.addstr(1, 0, "a=add  d=done  x=delete  c=completed  g=grind  /=search  f=filter  q=quit")
    stdscr.addstr(2, 0, "-" * 50)

    if subtitle:
        stdscr.addstr(3, 0, subtitle, curses.A_BOLD)

    cur = con.cursor()
    cur.execute(
        f"SELECT id, title, category, due, done, priority FROM todos WHERE deleted=0 AND done=0 {where_clause}",
        params,
    )
    todos = cur.fetchall()
    
    # Sort by priority (High > Medium > Low) then by id descending
    todos = sorted(todos, key=lambda t: (get_priority_order(t[5]), -t[0]))

    if not todos:
        stdscr.addstr(5, 0, "No todos yet!", curses.A_DIM)
    else:
        for idx, t in enumerate(todos):
            tid, title, cat, due_str, done, priority = t
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

            # Priority indicator with color
            priority_color = curses.color_pair(5) if priority == "High" else (
                curses.color_pair(2) if priority == "Medium" else curses.color_pair(6)
            )
            priority_symbol = "🔴" if priority == "High" else ("🟡" if priority == "Medium" else "🟢")

            marker = "-> " if idx == cursor_idx else "   "
            stdscr.addstr(5 + idx, 0, marker)
            stdscr.addstr(f"{prefix}", attr)
            stdscr.addstr(f"{priority_symbol} ", priority_color)
            stdscr.addstr(f"{title} ", attr)
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
        "SELECT id, title, category, due, priority FROM todos WHERE deleted=0 AND done=1 ORDER BY id DESC"
    )
    todos = cur.fetchall()

    if not todos:
        stdscr.addstr(3, 0, "No completed todos yet!", curses.A_DIM)
    else:
        for idx, t in enumerate(todos):
            tid, title, cat, due_str, priority = t
            priority_symbol = "🔴" if priority == "High" else ("🟡" if priority == "Medium" else "🟢")
            stdscr.addstr(3 + idx, 0, f"[x] {priority_symbol} {title} ")
            if cat:
                stdscr.addstr(f"#{cat}", curses.color_pair(4))
            if due_str:
                stdscr.addstr(f" (due {due_str})")

    stdscr.refresh()


def draw_daily_grind(stdscr, con):
    stdscr.clear()
    stdscr.addstr(0, 0, "💪 DAILY GRIND TRACKER", curses.A_BOLD)
    stdscr.addstr(1, 0, "Press 's' to set goal | 'b' to go back")
    stdscr.addstr(2, 0, "=" * 50)

    today = date.today()
    stdscr.addstr(4, 0, f"📅 Date: {today.strftime('%A, %B %d, %Y')}", curses.color_pair(4))

    # Get daily stats
    daily_goal = get_daily_goal(con)
    completed_today = get_today_completed(con)
    
    stdscr.addstr(6, 0, f"🎯 Daily Goal: {daily_goal} tasks")
    stdscr.addstr(7, 0, f"✅ Completed Today: {completed_today} tasks")
    
    # Progress calculation
    progress = int((completed_today / daily_goal) * 100) if daily_goal > 0 else 0
    progress = min(progress, 100)  # Cap at 100%
    
    stdscr.addstr(9, 0, "Progress:")
    draw_progress_bar(stdscr, 10, 0, progress, 40)
    
    # Motivational message
    stdscr.addstr(12, 0, "-" * 50)
    if progress >= 100:
        stdscr.addstr(13, 0, "🔥 BEAST MODE! You crushed today's goal! 🔥", curses.color_pair(3) | curses.A_BOLD)
    elif progress >= 75:
        stdscr.addstr(13, 0, "💪 Almost there! Keep pushing!", curses.color_pair(3))
    elif progress >= 50:
        stdscr.addstr(13, 0, "👍 Halfway there! You got this!", curses.color_pair(2))
    elif progress >= 25:
        stdscr.addstr(13, 0, "⚡ Good start! Keep the momentum!", curses.color_pair(2))
    else:
        stdscr.addstr(13, 0, "🚀 Let's get started! Grind time!", curses.color_pair(1))
    
    # Show today's completed tasks
    stdscr.addstr(15, 0, "Today's Completed Tasks:", curses.A_BOLD)
    stdscr.addstr(16, 0, "-" * 50)
    
    cur = con.cursor()
    today_iso = today.isoformat()
    cur.execute(
        "SELECT title, priority, category FROM todos WHERE deleted=0 AND done=1 AND completed_date=? ORDER BY id DESC",
        (today_iso,)
    )
    completed_tasks = cur.fetchall()
    
    if not completed_tasks:
        stdscr.addstr(17, 0, "No tasks completed yet today.", curses.A_DIM)
    else:
        for idx, task in enumerate(completed_tasks[:8]):  # Show max 8 tasks
            title, priority, category = task
            priority_symbol = "🔴" if priority == "High" else ("🟡" if priority == "Medium" else "🟢")
            stdscr.addstr(17 + idx, 0, f"  ✓ {priority_symbol} {title}")
            if category:
                stdscr.addstr(f" #{category}", curses.color_pair(4))
    
    stdscr.refresh()


# ---------- Main Loop ----------
def main(stdscr):
    con = init_db()
    curses.curs_set(0)
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)      # overdue
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)   # today / medium
    curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)    # future
    curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)     # category
    curses.init_pair(5, curses.COLOR_RED, curses.COLOR_BLACK)      # high priority
    curses.init_pair(6, curses.COLOR_GREEN, curses.COLOR_BLACK)    # low priority

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
        elif view == "grind":
            draw_daily_grind(stdscr, con)

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
                stdscr.addstr(3, 0, "Priority (High/Medium/Low) [Medium]: ")
                priority = stdscr.getstr().decode("utf-8").strip().capitalize()
                if priority not in ["High", "Medium", "Low"]:
                    priority = "Medium"
                curses.noecho()
                add_todo(con, title, category, due, priority)
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
            elif ch == ord("g"):
                view = "grind"
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
        elif view == "grind":
            if ch == ord("b"):
                view = "dashboard"
            elif ch == ord("s"):  # set daily goal
                curses.echo()
                stdscr.addstr(25, 0, "Set daily goal (number of tasks): ")
                try:
                    goal = int(stdscr.getstr().decode("utf-8"))
                    if goal > 0:
                        set_daily_goal(con, goal)
                except:
                    pass
                curses.noecho()


if __name__ == "__main__":
    curses.wrapper(main)