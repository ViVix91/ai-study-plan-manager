import streamlit as st
from datetime import date, timedelta, datetime, time
from math import ceil

# ---------- BASIC CONFIG ----------
st.set_page_config(
    page_title="AI Study Plan Manager",
    page_icon="📚",
    layout="wide"
)

# ---------- SESSION STATE SETUP ----------
if "plans" not in st.session_state:
    st.session_state.plans = []   # list of dicts: each dict = one subject/task

if "generated_for_today" not in st.session_state:
    st.session_state.generated_for_today = []   # tasks suggested for today

if "study_hours_today" not in st.session_state:
    st.session_state.study_hours_today = 3.0   # default 3hrs

if "exams" not in st.session_state:
    st.session_state.exams = []   # list of dicts: each exam in datesheet

if "syllabus_subjects" not in st.session_state:
    st.session_state.syllabus_subjects = []  # each: {subject, topics}


# ---------- COMMON AI HELPERS ----------

def analyse_subject_stats(tasks):
    """Return a dict: subject -> count of pending tasks."""
    stats = {}
    for t in tasks:
        subj = t["subject"]
        stats[subj] = stats.get(subj, 0) + 1
    return stats


def compute_priority_score(task, subject_stats, today=None):
    """
    Compute a priority score for a task using:
    - Urgency (deadline)
    - Difficulty
    - Hours required
    - Subject load (how many tasks for that subject)
    - Task type (New / Revision)
    """
    if today is None:
        today = date.today()

    # --- Urgency (0 to 1) ---
    days_left = (task["deadline"] - today).days
    if days_left <= 0:
        urgency = 1.0
    elif days_left > 30:
        urgency = 0.1
    else:
        urgency = 1 - (days_left / 30)

    # --- Difficulty (0 to 1) ---
    difficulty = (task.get("difficulty", 3) / 5.0)  # 1–5 -> 0.2–1.0

    # --- Hours factor (0 to 1) ---
    h = float(task.get("hours", 1))
    if h <= 1:
        hours_factor = 1.0
    elif h <= 2:
        hours_factor = 0.9
    elif h <= 4:
        hours_factor = 0.7
    elif h <= 6:
        hours_factor = 0.5
    else:
        hours_factor = 0.3

    # --- Subject load (0 to 1) ---
    subj = task["subject"]
    total_for_subject = subject_stats.get(subj, 1)
    if total_for_subject >= 5:
        subject_factor = 1.0
    elif total_for_subject == 4:
        subject_factor = 0.9
    elif total_for_subject == 3:
        subject_factor = 0.8
    elif total_for_subject == 2:
        subject_factor = 0.7
    else:
        subject_factor = 0.6

    # --- Task type: Revision gets a bit of boost near exams ---
    if task.get("task_type", "New") == "Revision":
        revision_factor = 1.0
    else:
        revision_factor = 0.8

    # Weighted sum
    score = (
        0.40 * urgency +
        0.25 * difficulty +
        0.15 * hours_factor +
        0.10 * subject_factor +
        0.10 * revision_factor
    )

    return round(score, 3)


def generate_today_plan(max_hours, planning_mode):
    """
    AI engine:
    - planning_mode = "Normal (All Subjects)" → use all pending tasks
    - planning_mode = "Day-Before-Exam Focus" → only tasks for tomorrow's exam subject
    """
    today = date.today()
    pending_tasks = [t for t in st.session_state.plans if t["status"] == "Pending"]

    if planning_mode == "Day-Before-Exam Focus":
        tomorrow = today + timedelta(days=1)
        exams_tomorrow = [e for e in st.session_state.exams if e["exam_date"] == tomorrow]

        if exams_tomorrow:
            subjects_tomorrow = {e["subject"] for e in exams_tomorrow}

            # Filter tasks only for those subjects / exam dates
            filtered = [
                t for t in pending_tasks
                if (t.get("exam_date") == tomorrow) or (t["subject"] in subjects_tomorrow)
            ]

            if not filtered:
                st.warning(
                    "I found an exam tomorrow, but there are **no study tasks** "
                    "for that subject yet. Generate a plan in **Exam Mode** or **Syllabus Planner** first."
                )
                return [], []

            pending_tasks = filtered
        else:
            st.warning(
                "No exam found for **tomorrow** in your datesheet. "
                "Using normal mode instead."
            )
            # keep all pending_tasks (no extra filtering)

    if not pending_tasks:
        return [], []

    subject_stats = analyse_subject_stats(pending_tasks)

    scored = []
    for t in pending_tasks:
        score = compute_priority_score(t, subject_stats)
        t_copy = t.copy()
        t_copy["ai_score"] = score
        scored.append(t_copy)

    # Sort by score descending
    scored.sort(key=lambda x: x["ai_score"], reverse=True)

    # Select tasks within time limit
    selected = []
    used_hours = 0.0
    for task in scored:
        hours = float(task.get("hours", 1))
        if used_hours + hours <= max_hours or not selected:
            selected.append(task)
            used_hours += hours

    return selected, scored


def generate_ai_insights(selected_tasks, total_hours_available, planning_mode):
    """Generate natural language 'AI coach' style insights."""
    if not selected_tasks:
        return "No tasks selected. Add tasks in **'Create Plan'**, **'Exam Mode'** or **'Smart Syllabus Planner'** first."

    total_time = sum(float(t["hours"]) for t in selected_tasks)
    by_subject = {}
    urgent_count = 0
    revision_count = 0
    new_count = 0

    today = date.today()
    for t in selected_tasks:
        subj = t["subject"]
        by_subject[subj] = by_subject.get(subj, 0) + 1

        if (t["deadline"] - today).days <= 2:
            urgent_count += 1
        if t.get("task_type", "New") == "Revision":
            revision_count += 1
        else:
            new_count += 1

    subject_part = ", ".join(
        f"{subj} ({cnt} task{'s' if cnt > 1 else ''})"
        for subj, cnt in by_subject.items()
    )

    text = []
    text.append(
        f"Planning mode: **{planning_mode}**."
    )
    text.append(
        f"Based on your available time of **{total_hours_available} hour(s)**, "
        f"I selected tasks totalling approximately **{round(total_time, 2)} hour(s)**."
    )

    if subject_part:
        text.append(
            f"Today's plan focuses on: **{subject_part}**."
        )

    if urgent_count > 0:
        text.append(
            f"I prioritised **{urgent_count} task(s)** with **very close deadlines** "
            f"to protect your exam days."
        )

    if revision_count > 0:
        text.append(
            f"There are **{revision_count} revision task(s)** and **{new_count} new learning task(s)** "
            f"so you revise and also cover remaining syllabus."
        )

    if total_time < total_hours_available * 0.6:
        text.append(
            "Your plan is slightly light. You could add a quick revision block or a small topic."
        )
    elif total_time > total_hours_available * 1.1:
        text.append(
            "Your plan is quite heavy. If it feels too much, drop one low-priority task or split a big one."
        )
    else:
        text.append("The workload looks well-balanced for today. 👍")

    return "\n\n".join(text)


# ---------- EXAM MODE: GENERATE PLAN FROM DATESHEET ----------

def generate_tasks_from_datesheet(start_date, default_session_hours=2.0):
    """
    For each exam in st.session_state.exams:
    - Use exam_date and estimated_hours.
    - Break it into study sessions of ~default_session_hours.
    - Spread sessions between start_date and (exam_date - 1).
    - Create tasks into st.session_state.plans.
    """
    exams = st.session_state.exams
    today = date.today()
    created_count = 0

    for exam in exams:
        subject = exam["subject"]
        exam_date = exam["exam_date"]
        total_hours = float(exam["hours"])
        difficulty = int(exam["difficulty"])

        # Skip exams that are already over or today
        if exam_date <= today:
            continue

        days_available = (exam_date - start_date).days
        if days_available <= 0:
            days_available = 1

        # Decide session size
        session_len = min(default_session_hours, total_hours)
        if session_len <= 0:
            continue

        sessions = max(1, ceil(total_hours / session_len))

        # Spread sessions across available days
        for i in range(sessions):
            day_index = int((i + 1) * days_available / (sessions + 1))
            session_deadline = start_date + timedelta(days=day_index)

            # ensure deadline before exam
            if session_deadline >= exam_date:
                session_deadline = exam_date - timedelta(days=1)
            if session_deadline < today:
                session_deadline = today

            hours_this = min(session_len, total_hours)
            total_hours -= hours_this

            task = {
                "subject": subject,
                "topic": f"{subject} Exam Prep Session {i+1}",
                "deadline": session_deadline,
                "hours": round(hours_this, 1),
                "difficulty": difficulty,
                "status": "Pending",
                "task_type": "Revision",
                "source": "Exam Mode",
                "exam_date": exam_date,
            }
            st.session_state.plans.append(task)
            created_count += 1

    return created_count


# ---------- DAILY TIMETABLE BUILDER ----------

def build_daily_schedule(selected_tasks, start_time: time, slot_minutes: int):
    """
    Turn selected tasks into an hour-by-hour timetable:
    - Start at start_time
    - Each slot = slot_minutes
    - Long tasks are split into Part 1, Part 2, ...
    """
    if not selected_tasks:
        return []

    schedule = []
    current_dt = datetime.combine(date.today(), start_time)
    slot_minutes = int(slot_minutes)

    for task in selected_tasks:
        minutes_left = int(float(task.get("hours", 1)) * 60)
        part = 1

        while minutes_left > 0:
            duration = min(slot_minutes, minutes_left)
            end_dt = current_dt + timedelta(minutes=duration)

            topic_label = task["topic"]
            if minutes_left > slot_minutes:
                topic_label = f"{task['topic']} (Part {part})"
            elif part > 1:
                topic_label = f"{task['topic']} (Part {part})"

            schedule.append({
                "Slot": len(schedule) + 1,
                "Start": current_dt.strftime("%H:%M"),
                "End": end_dt.strftime("%H:%M"),
                "Subject": task["subject"],
                "Topic": topic_label,
                "Planned Minutes": duration,
            })

            minutes_left -= duration
            current_dt = end_dt
            part += 1

    return schedule


# ---------- SYLLABUS PLANNER HELPERS ----------

def parse_topics_from_syllabus_text(text: str):
    """
    Simple parsing:
    - Split by lines
    - Remove empty lines
    - Treat each non-empty line as one topic
    """
    topics = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        topics.append(line)
    return topics


def generate_tasks_from_syllabus(subjects, exam_date, hours_per_topic, default_difficulty=3):
    """
    Take parsed syllabus topics for multiple subjects and spread them
    from today to exam_date - 1, then create tasks in st.session_state.plans.
    """
    today = date.today()
    if exam_date <= today:
        return 0

    # collect all (subject, topic) pairs
    all_items = []
    for subj in subjects:
        sname = subj["subject"]
        for topic in subj["topics"]:
            all_items.append((sname, topic))

    if not all_items:
        return 0

    days_available = (exam_date - today).days
    if days_available <= 0:
        days_available = 1

    total_topics = len(all_items)
    created = 0

    for i, (sname, topic) in enumerate(all_items):
        # spread topics across the range
        day_index = int((i + 1) * days_available / (total_topics + 1))
        deadline = today + timedelta(days=day_index)

        task = {
            "subject": sname,
            "topic": topic,
            "deadline": deadline,
            "hours": float(hours_per_topic),
            "difficulty": int(default_difficulty),
            "status": "Pending",
            "task_type": "New",
            "source": "Syllabus Planner",
            "exam_date": exam_date,
        }
        st.session_state.plans.append(task)
        created += 1

    return created


# ---------- UI SECTIONS ----------

def show_dashboard():
    st.title("📊 Dashboard & AI Study Coach")

    st.caption(
        f"🔍 I currently see **{len(st.session_state.plans)}** task(s), "
        f"**{len(st.session_state.exams)}** exam(s) in datesheet, "
        f"and **{len(st.session_state.syllabus_subjects)}** subject(s) in Syllabus Planner."
    )

    col1, col2, col3 = st.columns(3)
    total = len(st.session_state.plans)
    completed = sum(1 for t in st.session_state.plans if t["status"] == "Done")
    pending = total - completed

    with col1:
        st.metric("Total Tasks", total)
    with col2:
        st.metric("Completed", completed)
    with col3:
        st.metric("Pending", pending)

    st.markdown("---")

    # --- AI Planner Controls ---
    st.subheader("🧠 AI-Powered Today's Plan")

    st.write("Tell me how many hours you can actually study **today**, "
             "and I'll pick the best tasks for you.")

    colh1, colh2 = st.columns([1, 2])
    with colh1:
        hours = st.number_input(
            "Study hours today",
            min_value=1.0,
            max_value=16.0,
            step=0.5,
            value=float(st.session_state.study_hours_today)
        )
        st.session_state.study_hours_today = float(hours)

    with colh2:
        planning_mode = st.selectbox(
            "Planning Mode",
            ["Normal (All Subjects)", "Day-Before-Exam Focus"],
            help=(
                "Normal: balance all subjects.\n"
                "Day-Before-Exam Focus: only focus on the subject which has exam **tomorrow**."
            )
        )

    # --- Daily timetable settings (time slots) ---
    with st.expander("🗓️ Optional: Build Hour-by-Hour Timetable for Today"):
        colt1, colt2 = st.columns(2)
        with colt1:
            start_time = st.time_input(
                "Study day start time",
                value=time(9, 0)
            )
        with colt2:
            slot_minutes = st.number_input(
                "Each study slot length (minutes)",
                min_value=30,
                max_value=180,
                step=15,
                value=60
            )
        st.caption(
            "I’ll split your selected tasks into these time slots automatically "
            "and create a proper timetable."
        )

    generate_clicked = st.button("⚡ Generate / Refresh AI Plan", key="generate_ai_plan")

    all_scored_tasks = []

    if generate_clicked:
        if not st.session_state.plans:
            st.session_state.generated_for_today = []
            st.warning("No tasks yet. Use **'Create Plan'**, **'Exam Mode'** or **'Smart Syllabus Planner'** to add study tasks first.")
        else:
            selected, scored = generate_today_plan(
                st.session_state.study_hours_today,
                planning_mode
            )
            st.session_state.generated_for_today = selected
            all_scored_tasks = scored

    if not st.session_state.generated_for_today:
        st.info("Click the button above after adding tasks to see your AI-generated plan.")
        return

    # --- Show selected tasks ---
    total_time = sum(float(t["hours"]) for t in st.session_state.generated_for_today)
    st.success(
        f"AI selected **{len(st.session_state.generated_for_today)} task(s)** "
        f"(~{round(total_time, 2)} hr) for today."
    )

    for i, task in enumerate(st.session_state.generated_for_today, start=1):
        label = f"{i}. {task['subject']} - {task['topic']}  |  ⭐ Score: {task.get('ai_score', 0)}"
        if task.get("source") == "Exam Mode":
            label += "  📝 (Exam Mode)"
        if task.get("source") == "Syllabus Planner":
            label += "  📚 (Syllabus)"
        with st.expander(label):
            st.write(f"🎯 **Topic:** {task['topic']}")
            st.write(f"📘 **Subject:** {task['subject']}")
            st.write(f"⏱️ **Estimated Time:** {task['hours']} hr(s)")
            st.write(f"📆 **Deadline (study):** {task['deadline']}")
            if "exam_date" in task:
                st.write(f"🧪 **Exam Date:** {task['exam_date']}")
            st.write(f"🔥 **Difficulty:** {task['difficulty']}/5")
            st.write(f"🧩 **Type:** {task.get('task_type', 'New')}")
            st.write(f"📥 **Source:** {task.get('source', 'Manual')}")
            st.caption("Score is based on urgency, difficulty, subject load & revision priority.")

    st.markdown("---")
    st.subheader("🧩 AI Insights For You")
    insights = generate_ai_insights(
        st.session_state.generated_for_today,
        st.session_state.study_hours_today,
        planning_mode
    )
    st.write(insights)

    # --- Build and show auto timetable ---
    st.markdown("---")
    st.subheader("📆 Auto-Generated Timetable for Today")

    schedule = build_daily_schedule(
        st.session_state.generated_for_today,
        start_time,
        slot_minutes
    )

    if not schedule:
        st.info("No schedule generated. Try increasing your study hours or adding tasks.")
    else:
        st.dataframe(schedule, use_container_width=True)
        st.caption("You can follow this slot-by-slot timetable while studying today.")

    # Optional table of all tasks + scores
    if generate_clicked and all_scored_tasks:
        st.markdown("---")
        st.subheader("📋 All Tasks with AI Scores (for debug / analysis)")
        table_data = [
            {
                "Subject": t["subject"],
                "Topic": t["topic"],
                "Deadline": t["deadline"],
                "Hours": t["hours"],
                "Difficulty": t["difficulty"],
                "Status": t["status"],
                "Type": t.get("task_type", "New"),
                "Source": t.get("source", "Manual"),
                "AI Score": t["ai_score"],
            }
            for t in all_scored_tasks
        ]
        st.dataframe(table_data, use_container_width=True)


def show_create_plan():
    st.title("📝 Create Study Plan (Manual)")

    st.write("Add your own custom study tasks. The AI engine will prioritise them later.")

    with st.form("create_task_form"):
        subject = st.text_input("Subject (e.g., DSA, Maths, COA)")
        topic = st.text_input("Topic / Chapter (e.g., Sorting Algorithms, Trees)")
        today = date.today()
        default_deadline = today + timedelta(days=7)
        deadline = st.date_input("Target Date / Deadline", value=default_deadline, min_value=today)
        hours = st.number_input(
            "Estimated Hours Required",
            min_value=0.5,
            max_value=12.0,
            step=0.5
        )
        difficulty = st.slider("Difficulty Level", 1, 5, 3)
        task_type = st.selectbox("Task Type", ["New", "Revision"])
        submitted = st.form_submit_button("Add Task")

        if submitted:
            if subject.strip() == "" or topic.strip() == "":
                st.error("Please enter both **Subject** and **Topic**.")
            else:
                st.session_state.plans.append({
                    "subject": subject.strip(),
                    "topic": topic.strip(),
                    "deadline": deadline,
                    "hours": float(hours),
                    "difficulty": int(difficulty),
                    "status": "Pending",
                    "task_type": task_type,
                    "source": "Manual",
                })
                st.success("Task added to your study plan ✅")


def show_exam_mode():
    st.title("🧪 Exam Mode – Plan from Datesheet")

    st.write(
        "Add your **datesheet** (subject + exam date + approx hours needed), "
        "then generate a full study plan automatically."
    )

    st.subheader("1️⃣ Add Exams to Datesheet")

    with st.form("exam_form"):
        col1, col2 = st.columns(2)
        with col1:
            subject = st.text_input("Subject (as in your datesheet)")
        with col2:
            exam_date = st.date_input("Exam Date", min_value=date.today())

        col3, col4 = st.columns(2)
        with col3:
            hours = st.number_input(
                "Total Hours Needed for This Exam",
                min_value=1.0,
                max_value=100.0,
                step=1.0,
                value=10.0
            )
        with col4:
            difficulty = st.slider(
                "Overall Difficulty of This Subject",
                1, 5, 3
            )

        submitted = st.form_submit_button("Add Exam to Datesheet")

        if submitted:
            if subject.strip() == "":
                st.error("Please enter the subject name.")
            else:
                st.session_state.exams.append({
                    "subject": subject.strip(),
                    "exam_date": exam_date,
                    "hours": float(hours),
                    "difficulty": int(difficulty),
                })
                st.success("Exam added to datesheet ✅")

    if st.session_state.exams:
        st.markdown("---")
        st.subheader("📅 Your Datesheet")
        for idx, exam in enumerate(st.session_state.exams):
            with st.expander(f"{idx+1}. {exam['subject']} – Exam on {exam['exam_date']}"):
                st.write(f"🧪 **Subject:** {exam['subject']}")
                st.write(f"📆 **Exam Date:** {exam['exam_date']}")
                st.write(f"⏱️ **Total Study Hours Needed:** {exam['hours']} hr")
                st.write(f"🔥 **Difficulty:** {exam['difficulty']}/5")
                if st.button("Delete This Exam ❌", key=f"del_exam_{idx}"):
                    st.session_state.exams.pop(idx)
                    st.warning("Exam removed from datesheet.")
                    st.rerun()
    else:
        st.info("No exams added yet. Use the form above to add subjects from your datesheet.")

    st.markdown("---")
    st.subheader("2️⃣ Generate Study Plan From Datesheet")

    today = date.today()
    start_date = st.date_input(
        "Start Planning From (usually today)",
        value=today,
        min_value=today
    )

    default_session_hours = st.number_input(
        "Session Length (hours per study block)",
        min_value=0.5,
        max_value=6.0,
        step=0.5,
        value=2.0,
        help="Each subject's study is broken into blocks of this size."
    )

    if st.button("🚀 Generate Plan from Datesheet"):
        if not st.session_state.exams:
            st.error("Your datesheet is empty. Add at least one exam above first.")
        else:
            created = generate_tasks_from_datesheet(start_date, default_session_hours)
            if created == 0:
                st.warning("No tasks were created. Maybe all exams are already over or today.")
            else:
                st.success(
                    f"Created **{created}** study task(s) from your datesheet! "
                    "Go to **Dashboard** to let the AI pick today's tasks."
                )


def show_syllabus_planner():
    st.title("📚 Smart Syllabus Planner")

    st.write(
        "Just type or paste your **syllabus** for each subject "
        "(one topic per line) and I'll convert it into a study plan."
    )

    st.markdown("### 1️⃣ Overall Exam Info")

    today = date.today()
    exam_date = st.date_input(
        "Final Exam Date for these subjects",
        min_value=today + timedelta(days=1),
        value=today + timedelta(days=15)
    )

    hours_per_topic = st.number_input(
        "Average hours per topic",
        min_value=0.5,
        max_value=5.0,
        step=0.5,
        value=1.0,
        help="Used to estimate how long each topic takes."
    )

    default_difficulty = st.slider(
        "Default difficulty level for topics",
        1, 5, 3
    )

    st.markdown("### 2️⃣ Add Subjects + Typed Syllabus")

    with st.form("syllabus_form"):
        subject_name = st.text_input("Subject name")

        syllabus_text = st.text_area(
            "Syllabus topics (one line per topic/unit)",
            help="Example:\nUnit 1 – Sorting\nUnit 2 – Trees\nGraphs\nDynamic Programming\n...",
            height=200,
        )

        submitted = st.form_submit_button("Add Subject")

        if submitted:
            if subject_name.strip() == "":
                st.error("Please enter a subject name.")
            else:
                topics = parse_topics_from_syllabus_text(syllabus_text)
                if not topics:
                    st.error("I couldn't find any topics. Add at least one line.")
                else:
                    st.session_state.syllabus_subjects.append({
                        "subject": subject_name.strip(),
                        "topics": topics,
                    })
                    st.success(f"Added **{subject_name}** with **{len(topics)}** topics ✅")

    if st.session_state.syllabus_subjects:
        st.markdown("### 3️⃣ Current Syllabus Subjects")
        for idx, subj in enumerate(st.session_state.syllabus_subjects):
            with st.expander(f"{idx+1}. {subj['subject']} ({len(subj['topics'])} topics)"):
                st.write("📋 First few topics:")
                for t in subj["topics"][:10]:
                    st.write(f"- {t}")
                if len(subj["topics"]) > 10:
                    st.caption(f"... and {len(subj['topics']) - 10} more")
                if st.button("Remove this subject ❌", key=f"del_syllabus_{idx}"):
                    st.session_state.syllabus_subjects.pop(idx)
                    st.warning("Subject removed from Syllabus Planner.")
                    st.rerun()
    else:
        st.info("No subjects added yet. Use the form above to add a subject and its syllabus.")

    st.markdown("### 4️⃣ Generate Study Plan from Syllabus")

    if st.button("🚀 Create Tasks from Syllabus"):
        if not st.session_state.syllabus_subjects:
            st.error("Add at least one subject with syllabus topics first.")
        else:
            created = generate_tasks_from_syllabus(
                st.session_state.syllabus_subjects,
                exam_date,
                hours_per_topic,
                default_difficulty
            )
            if created == 0:
                st.warning("No tasks created. Check your exam date and syllabus topics.")
            else:
                st.success(
                    f"Created **{created}** study task(s) from your syllabus! "
                    "Go to **Dashboard** to let the AI plan and timetable your day."
                )


def show_view_edit():
    st.title("📂 View / Edit Study Plan")

    if not st.session_state.plans:
        st.info("No tasks yet. Use **'Create Plan'**, **'Exam Mode'** or **'Smart Syllabus Planner'** to add some.")
        return

    for idx, task in enumerate(st.session_state.plans):
        label = f"{idx+1}. {task['subject']} - {task['topic']}"
        if task.get("source") == "Exam Mode":
            label += "  📝 (Exam Mode)"
        if task.get("source") == "Syllabus Planner":
            label += "  📚 (Syllabus)"
        with st.expander(label):
            st.write(f"📘 **Subject:** {task['subject']}")
            st.write(f"🎯 **Topic:** {task['topic']}")
            st.write(f"📆 **Deadline (study):** {task['deadline']}")
            if "exam_date" in task:
                st.write(f"🧪 **Exam Date:** {task['exam_date']}")
            st.write(f"⏱️ **Estimated Hours:** {task['hours']} hr(s)")
            st.write(f"🔥 **Difficulty:** {task['difficulty']}/5")
            st.write(f"🧩 **Type:** {task.get('task_type', 'New')}")
            st.write(f"📥 **Source:** {task.get('source', 'Manual')}")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Mark as Done ✅", key=f"done_{idx}"):
                    st.session_state.plans[idx]["status"] = "Done"
                    st.success("Marked as Done")
                    st.rerun()
            with col2:
                if st.button("Delete 🗑️", key=f"delete_{idx}"):
                    st.session_state.plans.pop(idx)
                    st.warning("Task deleted")
                    st.rerun()


# ---------- SIDEBAR NAV ----------
with st.sidebar:
    st.title("📚 AI Study Plan Manager")
    page = st.radio(
        "Go to:",
        ["Dashboard", "Create Plan", "Exam Mode", "Smart Syllabus Planner", "View / Edit Plan"]
    )
    st.markdown("---")
    st.caption("Made with ❤️ in Python & Streamlit             by Aaditya")

# ---------- PAGE ROUTING ----------
if page == "Dashboard":
    show_dashboard()
elif page == "Create Plan":
    show_create_plan()
elif page == "Exam Mode":
    show_exam_mode()
elif page == "Smart Syllabus Planner":
    show_syllabus_planner()
elif page == "View / Edit Plan":
    show_view_edit()
