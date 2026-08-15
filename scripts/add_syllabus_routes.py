#!/usr/bin/env python3
"""
scripts/add_syllabus_routes.py
Appends the Syllabus Catalog Management UI functions and FastAPI/FastHTML routes to app.py.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PY = os.path.join(BASE_DIR, "app.py")

with open(APP_PY, "r", encoding="utf-8") as f:
    content = f.read()

syllabus_ui_and_routes = """

# =============================================================================
# 13.5) SYLLABUS CATALOG MANAGEMENT UI & ROUTES
# =============================================================================

def page_syllabus_manager() -> Tuple:
    \"\"\"Syllabus Catalog Registry & Management Overview Page.\"\"\"
    registry = load_registry()
    depts = registry.get("departments", [])
    
    # Draft files in syllabus_drafts
    drafts_dir = os.path.join(os.path.dirname(__file__), "syllabus_drafts")
    draft_files = []
    if os.path.isdir(drafts_dir):
        for f in os.listdir(drafts_dir):
            if f.endswith(".json"):
                fpath = os.path.join(drafts_dir, f)
                try:
                    with open(fpath, "r", encoding="utf-8") as jf:
                        ddata = json.load(jf)
                    draft_files.append({
                        "file": f,
                        "draft_id": ddata.get("draft_id", f.replace(".json", "")),
                        "department": ddata.get("department", "Unknown"),
                        "department_code": ddata.get("department_code", ""),
                        "regulation": ddata.get("regulation", "R2024"),
                        "status": ddata.get("status", "REVIEW_REQUIRED"),
                        "course_count": len(ddata.get("courses", [])),
                        "needs_review": ddata.get("needs_review_count", 0)
                    })
                except Exception:
                    pass

    # 1. Registered Department Catalogs Table
    dept_rows = []
    for d in depts:
        code = d.get("code", "")
        name = d.get("name", "")
        catalogs = d.get("catalogs", {})
        
        for reg, cinfo in catalogs.items():
            st = cinfo.get("status", "ACTIVE")
            badge = "bg-green-100 text-green-800" if st == "ACTIVE" else "bg-slate-100 text-slate-800"
            ver = cinfo.get("version", "1.0")
            h = cinfo.get("hash", "")[:10] + "..." if cinfo.get("hash") else "—"
            dept_rows.append(Tr(
                Td(Span(code, cls="font-mono font-bold text-slate-900"), cls="px-4 py-3 border-b text-xs"),
                Td(name, cls="px-4 py-3 border-b text-xs font-medium text-slate-800"),
                Td(Span(reg, cls="font-bold text-blue-700"), cls="px-4 py-3 border-b text-xs"),
                Td(f"v{ver}", cls="px-4 py-3 border-b text-xs font-mono text-slate-600"),
                Td(Span(h, cls="font-mono text-[11px] text-slate-500"), cls="px-4 py-3 border-b text-xs"),
                Td(Span(st, cls=f"px-2 py-0.5 text-[10px] font-bold rounded-full {badge}"), cls="px-4 py-3 border-b text-xs"),
                Td(
                    Span("✓ Published & Active", cls="text-xs text-green-700 font-semibold"),
                    cls="px-4 py-3 border-b text-xs"
                )
            ))
        if not catalogs:
            dept_rows.append(Tr(
                Td(Span(code, cls="font-mono font-bold text-slate-500"), cls="px-4 py-3 border-b text-xs"),
                Td(name, cls="px-4 py-3 border-b text-xs text-slate-600"),
                Td("—", cls="px-4 py-3 border-b text-xs text-slate-400"),
                Td("—", cls="px-4 py-3 border-b text-xs text-slate-400"),
                Td("—", cls="px-4 py-3 border-b text-xs text-slate-400"),
                Td(Span("UNAVAILABLE", cls="px-2 py-0.5 text-[10px] font-bold rounded-full bg-slate-100 text-slate-500"), cls="px-4 py-3 border-b text-xs"),
                Td(
                    Span("Upload PDF below to initialize", cls="text-xs text-slate-400 italic"),
                    cls="px-4 py-3 border-b text-xs"
                )
            ))

    registry_card = Div(
        Div(
            H3("Academic Department Syllabus Registry", cls="text-base font-extrabold text-slate-900"),
            Span("Authoritative academic source data for course codes, credits, and semester categories", cls="text-xs text-slate-500 block mt-0.5"),
            cls="mb-4"
        ),
        Div(
            Table(
                Thead(Tr(
                    Th("Dept Code", cls="px-4 py-2.5 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                    Th("Department / Programme Name", cls="px-4 py-2.5 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                    Th("Regulation", cls="px-4 py-2.5 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                    Th("Version", cls="px-4 py-2.5 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                    Th("Catalog Hash", cls="px-4 py-2.5 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                    Th("Status", cls="px-4 py-2.5 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                    Th("Actions / State", cls="px-4 py-2.5 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                )),
                Tbody(*dept_rows),
                cls="w-full border border-slate-200 rounded-lg overflow-hidden"
            ),
            cls="overflow-x-auto mb-2"
        ),
        cls="card p-6 mb-8"
    )

    # 2. Upload New Syllabus PDF Card
    upload_syllabus_card = Div(
        Div(
            H3("Upload New or Updated Syllabus PDF", cls="text-base font-extrabold text-slate-900"),
            P("Deterministically extracts curriculum tables (Semesters I–VIII), course codes, credits, and categories into a stage draft for review.", cls="text-xs text-slate-500 mb-4"),
            Form(
                Div(
                    Div(
                        Label("Target Department:", cls="block text-xs font-bold text-slate-700 mb-1"),
                        Select(
                            *[Option(f"{d['name']} ({d['code']})", value=d['code']) for d in depts],
                            name="dept_code", required=True,
                            cls="block w-full text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500"
                        ),
                        cls="flex-1"
                    ),
                    Div(
                        Label("Regulation Code:", cls="block text-xs font-bold text-slate-700 mb-1"),
                        Input(type="text", name="regulation", value="R2024", placeholder="e.g. R2024, R2027", required=True,
                              cls="block w-full text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-lg p-2.5 focus:ring-2 focus:ring-blue-500"),
                        cls="w-36"
                    ),
                    Div(
                        Label("Syllabus PDF File:", cls="block text-xs font-bold text-slate-700 mb-1"),
                        Input(type="file", name="syllabus_pdf", accept=".pdf", required=True,
                              cls="block w-full text-xs text-slate-600 bg-white border border-slate-200 rounded-lg p-2 cursor-pointer"),
                        cls="flex-1"
                    ),
                    Div(
                        Label(NotStr("&nbsp;"), cls="block text-xs mb-1"),
                        Button("Extract Syllabus →", type="submit",
                               cls="px-5 py-2.5 text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors shadow-xs"),
                        cls="flex items-end"
                    ),
                    cls="flex flex-wrap items-end gap-3"
                ),
                action="/syllabus/upload", method="POST", enctype="multipart/form-data"
            ),
            cls="mb-2"
        ),
        cls="card p-6 mb-8 border-t-4 border-t-blue-600"
    )

    # 3. Draft Syllabi Table
    draft_rows = []
    for dr in draft_files:
        badge_cls = "bg-amber-100 text-amber-800" if dr["needs_review"] > 0 else "bg-blue-100 text-blue-800"
        draft_rows.append(Tr(
            Td(Span(dr["draft_id"], cls="font-mono text-xs font-bold text-slate-900"), cls="px-4 py-3 border-b"),
            Td(Span(f"{dr['department']} ({dr['department_code']})", cls="text-xs font-medium text-slate-800"), cls="px-4 py-3 border-b"),
            Td(Span(dr["regulation"], cls="text-xs font-bold text-blue-700"), cls="px-4 py-3 border-b"),
            Td(Span(str(dr["course_count"]), cls="text-xs font-bold text-slate-800"), cls="px-4 py-3 border-b"),
            Td(Span(str(dr["needs_review"]), cls=f"text-xs font-bold {'text-amber-700' if dr['needs_review'] > 0 else 'text-slate-500'}"), cls="px-4 py-3 border-b"),
            Td(Span(dr["status"], cls=f"px-2 py-0.5 text-[10px] font-bold rounded-full {badge_cls}"), cls="px-4 py-3 border-b"),
            Td(
                Div(
                    A("Review & Publish →", href=f"/syllabus/draft/{dr['draft_id']}",
                      cls="px-3 py-1 text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors inline-block mr-2"),
                    Form(
                        Input(type="hidden", name="draft_id", value=dr["draft_id"]),
                        Button("Delete", type="submit", cls="px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50 rounded border border-red-200 transition-colors"),
                        action=f"/syllabus/delete-draft/{dr['draft_id']}", method="POST", cls="inline-block"
                    ),
                    cls="flex items-center"
                ),
                cls="px-4 py-3 border-b"
            )
        ))

    drafts_card = Div(
        H3("Syllabus Stage Drafts (Unpublished)", cls="text-base font-extrabold text-slate-900 mb-2"),
        P("Drafts are isolated in syllabus_drafts/ and are NOT active until reviewed and approved.", cls="text-xs text-slate-500 mb-4"),
        Div(
            Table(
                Thead(Tr(
                    Th("Draft ID", cls="px-4 py-2 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                    Th("Department", cls="px-4 py-2 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                    Th("Regulation", cls="px-4 py-2 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                    Th("Courses", cls="px-4 py-2 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                    Th("Needs Review", cls="px-4 py-2 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                    Th("State", cls="px-4 py-2 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                    Th("Actions", cls="px-4 py-2 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                )),
                Tbody(*draft_rows),
                cls="w-full border border-slate-200 rounded-lg overflow-hidden"
            ) if draft_rows else P("No pending syllabus drafts. Upload a PDF above to create a new draft catalog.", cls="text-xs text-slate-400 p-4 bg-slate-50 rounded-lg text-center"),
            cls="overflow-x-auto"
        ),
        cls="card p-6"
    )

    return layout("Syllabus Catalogs", "syllabus", Div(
        Div(
            H1("Academic Syllabus Catalogs & Registry", cls="text-2xl font-bold text-slate-800 mb-1"),
            P("Dynamic academic source of truth for regulations, courses, and department syllabi.", cls="text-sm text-slate-500 mb-6"),
        ),
        registry_card,
        upload_syllabus_card,
        drafts_card,
        cls="max-w-6xl mx-auto"
    ))


def page_syllabus_draft_review(draft_data: Dict[str, Any], draft_id: str) -> Tuple:
    \"\"\"Interactive Syllabus Draft Review & Publication Editor Page.\"\"\"
    courses = draft_data.get("courses", [])
    dept = draft_data.get("department", "")
    dept_code = draft_data.get("department_code", "")
    reg = draft_data.get("regulation", "")
    needs_review = draft_data.get("needs_review_count", 0)

    course_rows = []
    for idx, c in enumerate(courses):
        code_val = c.get("code", "")
        name_val = c.get("name", "")
        cred_val = c.get("credits", 3.0)
        sem_val = c.get("semester", 1)
        type_val = c.get("type", "THEORY")
        st_val = c.get("status", "VERIFIED")
        conf_val = c.get("confidence", 1.0)
        aliases_str = ", ".join(c.get("aliases", []))

        badge = "bg-green-100 text-green-800" if st_val == "VERIFIED" else "bg-amber-100 text-amber-800"

        course_rows.append(Tr(
            Td(
                Input(type="text", name=f"code_{idx}", value=code_val, required=True,
                      cls="w-28 text-xs font-mono font-bold p-1.5 border border-slate-200 rounded focus:ring-1 focus:ring-blue-500"),
                cls="px-3 py-2 border-b"
            ),
            Td(
                Input(type="text", name=f"name_{idx}", value=name_val, required=True,
                      cls="w-full text-xs font-medium p-1.5 border border-slate-200 rounded focus:ring-1 focus:ring-blue-500"),
                cls="px-3 py-2 border-b"
            ),
            Td(
                Input(type="number", name=f"credits_{idx}", value=cred_val, step="0.5", min="0", max="20", required=True,
                      cls="w-16 text-xs text-center p-1.5 border border-slate-200 rounded focus:ring-1 focus:ring-blue-500"),
                cls="px-3 py-2 border-b"
            ),
            Td(
                Select(
                    *[Option(f"Sem {s}", value=str(s), selected=(int(sem_val) == s)) for s in range(1, 9)],
                    name=f"sem_{idx}",
                    cls="w-20 text-xs p-1.5 border border-slate-200 rounded focus:ring-1 focus:ring-blue-500"
                ),
                cls="px-3 py-2 border-b"
            ),
            Td(
                Select(
                    Option("THEORY", value="THEORY", selected=(type_val == "THEORY")),
                    Option("LAB", value="LAB", selected=(type_val == "LAB")),
                    Option("THEORY_CUM_PRACTICAL", value="THEORY_CUM_PRACTICAL", selected=(type_val == "THEORY_CUM_PRACTICAL")),
                    Option("PROJECT", value="PROJECT", selected=(type_val == "PROJECT")),
                    name=f"type_{idx}",
                    cls="w-28 text-xs p-1.5 border border-slate-200 rounded focus:ring-1 focus:ring-blue-500"
                ),
                cls="px-3 py-2 border-b"
            ),
            Td(
                Input(type="text", name=f"aliases_{idx}", value=aliases_str,
                      placeholder="e.g. ML, MACHINE LEARNING",
                      cls="w-full text-xs p-1.5 border border-slate-200 rounded focus:ring-1 focus:ring-blue-500"),
                cls="px-3 py-2 border-b"
            ),
            Td(
                Span(st_val, cls=f"px-2 py-0.5 text-[10px] font-bold rounded-full {badge}"),
                cls="px-3 py-2 border-b text-center"
            )
        ))

    return layout(f"Review Draft: {dept_code} {reg}", "syllabus", Div(
        Div(
            Div(
                A("← Back to Syllabus Manager", href="/syllabus", cls="text-xs font-bold text-blue-600 hover:text-blue-800 mb-2 inline-block"),
                H1(f"Review Syllabus Draft: {dept} ({reg})", cls="text-2xl font-bold text-slate-800 mb-1"),
                P(f"Draft ID: {draft_id} · Extracted Courses: {len(courses)} · Review Required: {needs_review}", cls="text-sm text-slate-500"),
            ),
            cls="mb-6"
        ),
        Form(
            Div(
                Table(
                    Thead(Tr(
                        Th("Course Code", cls="px-3 py-2.5 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                        Th("Course Title", cls="px-3 py-2.5 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                        Th("Credits", cls="px-3 py-2.5 text-center text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                        Th("Semester", cls="px-3 py-2.5 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                        Th("Type", cls="px-3 py-2.5 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                        Th("Aliases (Comma Separated)", cls="px-3 py-2.5 text-left text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                        Th("Status", cls="px-3 py-2.5 text-center text-xs font-bold text-slate-600 bg-slate-50 border-b"),
                    )),
                    Tbody(*course_rows),
                    cls="w-full border border-slate-200 rounded-lg overflow-hidden"
                ),
                cls="overflow-x-auto mb-6"
            ),
            Div(
                Button("Save Draft Changes", type="submit",
                       formaction=f"/syllabus/save-draft/{draft_id}",
                       cls="px-5 py-2.5 text-xs font-bold bg-slate-800 hover:bg-slate-900 text-white rounded-lg transition-colors shadow-xs mr-3"),
                Button("✓ Approve & Publish Catalog", type="submit",
                       formaction=f"/syllabus/publish/{draft_id}",
                       cls="px-6 py-2.5 text-xs font-bold bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors shadow-md"),
                cls="flex items-center justify-end"
            ),
            method="POST",
            cls="card p-6 mb-8"
        ),
        cls="max-w-6xl mx-auto"
    ))


@app.get("/syllabus")
def route_syllabus_manager():
    return page_syllabus_manager()


@app.post("/syllabus/upload")
async def route_syllabus_upload(request):
    try:
        form = await request.form()
        file = form.get("syllabus_pdf")
        if not file or not getattr(file, "filename", ""):
            push_alert("Please select a syllabus PDF file to extract.", "red")
            return RedirectResponse("/syllabus", status_code=303)

        dept_code = str(form.get("dept_code", "AI_DS")).strip().upper()
        reg_code = str(form.get("regulation", "R2024")).strip().upper()

        pdf_bytes = await file.read()
        res = extract_syllabus_pdf(pdf_bytes, department_code_hint=dept_code, regulation_hint=reg_code)
        
        push_alert(f"Syllabus PDF extracted: {res['draft_data']['total_courses_extracted']} courses detected in draft.", "green")
        return RedirectResponse(f"/syllabus/draft/{res['draft_id']}", status_code=303)
    except Exception as e:
        push_alert(f"Syllabus PDF extraction error: {e}", "red")
        return RedirectResponse("/syllabus", status_code=303)


@app.get("/syllabus/draft/{draft_id}")
def route_syllabus_draft_get(draft_id: str):
    drafts_dir = os.path.join(os.path.dirname(__file__), "syllabus_drafts")
    fpath = None
    if os.path.isdir(drafts_dir):
        for f in os.listdir(drafts_dir):
            if draft_id in f and f.endswith(".json"):
                fpath = os.path.join(drafts_dir, f)
                break

    if not fpath or not os.path.isfile(fpath):
        push_alert(f"Draft '{draft_id}' not found.", "red")
        return RedirectResponse("/syllabus", status_code=303)

    with open(fpath, "r", encoding="utf-8") as jf:
        ddata = json.load(jf)

    return page_syllabus_draft_review(ddata, draft_id)


@app.post("/syllabus/save-draft/{draft_id}")
async def route_syllabus_save_draft(request, draft_id: str):
    try:
        form = await request.form()
        drafts_dir = os.path.join(os.path.dirname(__file__), "syllabus_drafts")
        fpath = None
        for f in os.listdir(drafts_dir):
            if draft_id in f and f.endswith(".json"):
                fpath = os.path.join(drafts_dir, f)
                break

        if not fpath:
            push_alert("Draft file not found.", "red")
            return RedirectResponse("/syllabus", status_code=303)

        with open(fpath, "r", encoding="utf-8") as jf:
            ddata = json.load(jf)

        courses = ddata.get("courses", [])
        for idx in range(len(courses)):
            c_code = form.get(f"code_{idx}")
            c_name = form.get(f"name_{idx}")
            c_cred = form.get(f"credits_{idx}")
            c_sem = form.get(f"sem_{idx}")
            c_type = form.get(f"type_{idx}")
            c_aliases_raw = form.get(f"aliases_{idx}")

            if c_code:
                courses[idx]["code"] = str(c_code).strip().upper()
            if c_name:
                courses[idx]["name"] = str(c_name).strip()
            if c_cred:
                courses[idx]["credits"] = float(c_cred)
            if c_sem:
                courses[idx]["semester"] = int(c_sem)
            if c_type:
                courses[idx]["type"] = str(c_type).strip()
            if c_aliases_raw is not None:
                aliases_list = [a.strip() for a in str(c_aliases_raw).split(",") if a.strip()]
                courses[idx]["aliases"] = aliases_list
            courses[idx]["status"] = "VERIFIED"

        ddata["courses"] = courses
        ddata["needs_review_count"] = 0
        ddata["status"] = "REVIEWED"

        with open(fpath, "w", encoding="utf-8") as jf:
            json.dump(ddata, jf, indent=2, ensure_ascii=False)

        push_alert("Draft changes saved successfully.", "green")
        return RedirectResponse(f"/syllabus/draft/{draft_id}", status_code=303)
    except Exception as e:
        push_alert(f"Save draft error: {e}", "red")
        return RedirectResponse("/syllabus", status_code=303)


@app.post("/syllabus/publish/{draft_id}")
async def route_syllabus_publish(request, draft_id: str):
    try:
        drafts_dir = os.path.join(os.path.dirname(__file__), "syllabus_drafts")
        fpath = None
        for f in os.listdir(drafts_dir):
            if draft_id in f and f.endswith(".json"):
                fpath = os.path.join(drafts_dir, f)
                break

        if not fpath:
            push_alert("Draft file not found.", "red")
            return RedirectResponse("/syllabus", status_code=303)

        with open(fpath, "r", encoding="utf-8") as jf:
            ddata = json.load(jf)

        # Publish catalog
        pub_result = publish_syllabus_draft(ddata, actor="Faculty Academic Committee")

        # Remove published draft
        try:
            os.remove(fpath)
        except Exception:
            pass

        push_alert(
            f"Successfully published {pub_result['department_code']} {pub_result['regulation']} catalog! "
            f"{pub_result['course_count']} courses active (Checksum: {pub_result['catalog_hash'][:8]}...).",
            "green"
        )
        return RedirectResponse("/syllabus", status_code=303)
    except CatalogValidationError as cve:
        push_alert(f"Validation Block: {cve}", "red")
        return RedirectResponse(f"/syllabus/draft/{draft_id}", status_code=303)
    except Exception as e:
        push_alert(f"Publish error: {e}", "red")
        return RedirectResponse("/syllabus", status_code=303)


@app.post("/syllabus/delete-draft/{draft_id}")
def route_syllabus_delete_draft(draft_id: str):
    try:
        drafts_dir = os.path.join(os.path.dirname(__file__), "syllabus_drafts")
        for f in os.listdir(drafts_dir):
            if draft_id in f and f.endswith(".json"):
                os.remove(os.path.join(drafts_dir, f))
                break
        push_alert(f"Draft '{draft_id}' deleted.", "blue")
    except Exception as e:
        push_alert(f"Delete draft error: {e}", "red")
    return RedirectResponse("/syllabus", status_code=303)
"""

if "@app.get(\"/syllabus\")" not in content:
    startup_marker = "# =============================================================================\n# 14) APPLICATION STARTUP"
    if startup_marker in content:
        content = content.replace(startup_marker, syllabus_ui_and_routes + "\n\n" + startup_marker)
    else:
        content += syllabus_ui_and_routes

with open(APP_PY, "w", encoding="utf-8") as f:
    f.write(content)

print("Successfully added syllabus UI and routes to app.py")
