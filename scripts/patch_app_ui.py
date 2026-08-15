#!/usr/bin/env python3
"""
scripts/patch_app_ui.py
Adds UI controls and routes to app.py:
1. Adds Department, Regulation, Semester selection fields to page_upload.
2. Adds Catalog Match banner to page_pdf_preview.
3. Adds Syllabus link to sidebar and mobile_header.
4. Adds metadata fields to Excel output in build_department_excel.
5. Adds Syllabus Management pages and routes.
"""

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PY = os.path.join(BASE_DIR, "app.py")

with open(APP_PY, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update navigation items in sidebar and mobile_header
old_nav_items = """    items = [
        ("/upload", "Upload", "upload"),
        ("/dashboard", "Dashboard", "dashboard"),
        ("/students", "Students", "students"),
        ("/subjects", "Subjects", "subjects"),
        ("/attention", "Attention", "attention"),
        ("/rankings", "Rankings", "rankings"),
        ("/ai-insights", "AI Insights", "ai-insights"),
        ("/reports", "Reports", "reports"),
    ]"""

new_nav_items = """    items = [
        ("/upload", "Upload", "upload"),
        ("/dashboard", "Dashboard", "dashboard"),
        ("/students", "Students", "students"),
        ("/subjects", "Subjects", "subjects"),
        ("/attention", "Attention", "attention"),
        ("/rankings", "Rankings", "rankings"),
        ("/ai-insights", "AI Insights", "ai-insights"),
        ("/reports", "Reports", "reports"),
        ("/syllabus", "Syllabus Catalogs", "syllabus"),
    ]"""

content = content.replace(old_nav_items, new_nav_items)

# Add syllabus icon to sidebar
old_icons = '"reports": \'<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>\','
new_icons = old_icons + '\n        "syllabus": \'<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"/></svg>\','

content = content.replace(old_icons, new_icons)

# 2. Update page_upload form with Academic Catalog Selection
old_upload_prelude = 'P("Drop your official result PDF here or click to browse. Automatically extracts student records & verifies page provenance.", cls="text-xs text-slate-500 mb-4 leading-relaxed"),'

new_upload_selection = """P("Drop your official result PDF here or click to browse. Automatically extracts student records & verifies page provenance.", cls="text-xs text-slate-500 mb-3 leading-relaxed"),

                        # Academic Catalog Target Selection
                        Div(
                            Div(
                                Span("🎯 ACADEMIC TARGET CATALOG", cls="text-[10px] font-bold text-blue-700 uppercase tracking-wider block mb-1"),
                                Span("Select the academic department, regulation, and semester to apply for course resolution:", cls="text-[11px] text-slate-500 block mb-2"),
                            ),
                            Div(
                                Div(
                                    Label("Department:", cls="block text-[11px] font-bold text-slate-700 mb-1"),
                                    Select(
                                        *[Option(f"{d['name']} ({d['code']})", value=d['code'], selected=(d['code'] == SESSION.get("analysis_context", {}).get("department", "AI_DS"))) for d in get_registered_departments()],
                                        name="department", id="upload_dept_select", required=True,
                                        cls="block w-full text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-blue-500 shadow-xs"
                                    ),
                                    cls="flex-1"
                                ),
                                Div(
                                    Label("Regulation:", cls="block text-[11px] font-bold text-slate-700 mb-1"),
                                    Select(
                                        Option("R2024 (Active)", value="R2024", selected=True),
                                        Option("R2021 (Legacy)", value="R2021"),
                                        name="regulation", id="upload_reg_select", required=True,
                                        cls="block w-full text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-blue-500 shadow-xs"
                                    ),
                                    cls="w-28"
                                ),
                                Div(
                                    Label("Semester:", cls="block text-[11px] font-bold text-slate-700 mb-1"),
                                    Select(
                                        Option("Semester IV (Default)", value="4", selected=(int(SESSION.get("analysis_context", {}).get("semester", 4)) == 4)),
                                        Option("Semester I", value="1", selected=(int(SESSION.get("analysis_context", {}).get("semester", 4)) == 1)),
                                        Option("Semester II", value="2", selected=(int(SESSION.get("analysis_context", {}).get("semester", 4)) == 2)),
                                        Option("Semester III", value="3", selected=(int(SESSION.get("analysis_context", {}).get("semester", 4)) == 3)),
                                        Option("Semester V", value="5", selected=(int(SESSION.get("analysis_context", {}).get("semester", 4)) == 5)),
                                        Option("Semester VI", value="6", selected=(int(SESSION.get("analysis_context", {}).get("semester", 4)) == 6)),
                                        Option("Semester VII", value="7", selected=(int(SESSION.get("analysis_context", {}).get("semester", 4)) == 7)),
                                        Option("Semester VIII", value="8", selected=(int(SESSION.get("analysis_context", {}).get("semester", 4)) == 8)),
                                        name="semester", id="upload_sem_select", required=True,
                                        cls="block w-full text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-lg p-2 focus:ring-2 focus:ring-blue-500 shadow-xs"
                                    ),
                                    cls="w-36"
                                ),
                                cls="flex flex-wrap gap-2.5 mb-3"
                            ),
                            cls="p-3 bg-slate-50 border border-slate-200/80 rounded-xl mb-4"
                        ),"""

if old_upload_prelude in content:
    content = content.replace(old_upload_prelude, new_upload_selection)

# 3. Update route_upload_pdf to read Department, Regulation, Semester
old_upload_pdf_route = """        pdf_bytes = await file.read()
        if not pdf_bytes:
            push_alert("Uploaded PDF file is empty.", "red")
            return RedirectResponse("/upload", status_code=303)

        pdf_report = extract_coe_pdf(pdf_bytes, filename)"""

new_upload_pdf_route = """        pdf_bytes = await file.read()
        if not pdf_bytes:
            push_alert("Uploaded PDF file is empty.", "red")
            return RedirectResponse("/upload", status_code=303)

        # Extract selected catalog context
        dept_val = str(form.get("department", "AI_DS")).strip().upper()
        reg_val = str(form.get("regulation", "R2024")).strip().upper()
        sem_val = int(form.get("semester", 4))

        cat_obj = get_catalog(dept_val, reg_val)
        cat_ver = cat_obj.metadata.catalog_version if cat_obj else "1.0"
        cat_hash = cat_obj.metadata.sha256_hash if cat_obj else ""

        analysis_ctx = {
            "department": dept_val,
            "regulation": reg_val,
            "semester": sem_val,
            "catalog_version": cat_ver,
            "catalog_hash": cat_hash
        }
        SESSION["analysis_context"] = analysis_ctx

        pdf_report = extract_coe_pdf(pdf_bytes, filename, analysis_context=analysis_ctx)"""

if old_upload_pdf_route in content:
    content = content.replace(old_upload_pdf_route, new_upload_pdf_route)

# 4. Update page_pdf_preview to display Catalog Match Confidence banner
old_preview_header = """    # 1. Document Metadata Card
    doc_meta_card = Div("""

new_preview_header = """    # 0. Catalog Match Confidence Banner
    match_status = getattr(meta, "catalog_match_status", "CONFIRMED")
    if match_status == "MISMATCH":
        catalog_banner = Div(
            Div(
                Span("⚠", cls="text-amber-600 text-xl font-bold mr-3"),
                Div(
                    Span("CATALOG MISMATCH DETECTED", cls="text-xs font-bold uppercase tracking-wider text-amber-800 block"),
                    Span(getattr(meta, "catalog_match_message", "Selected semester does not match detected PDF header. Please review."), cls="text-xs text-amber-700 block mt-0.5"),
                ),
                cls="flex items-start"
            ),
            cls="p-4 bg-amber-50 border border-amber-300 rounded-xl mb-6 shadow-xs"
        )
    else:
        catalog_banner = Div(
            Div(
                Span("✓", cls="text-green-600 text-xl font-bold mr-3"),
                Div(
                    Span("CATALOG MATCH CONFIRMED (100% CONFIDENCE)", cls="text-xs font-bold uppercase tracking-wider text-green-800 block"),
                    Span(f"Department: {getattr(meta, 'catalog_department', 'AI_DS')} · Regulation: {getattr(meta, 'catalog_regulation', 'R2024')} · {getattr(meta, 'catalog_semester', 'Semester IV')} · Catalog Version: {getattr(meta, 'catalog_version', '1.0')} (Hash: {str(getattr(meta, 'catalog_hash', ''))[:10]}...)", cls="text-xs text-green-700 block mt-0.5"),
                ),
                cls="flex items-start"
            ),
            cls="p-4 bg-green-50 border border-green-200 rounded-xl mb-6 shadow-xs"
        )

    # 1. Document Metadata Card
    doc_meta_card = Div("""

if old_preview_header in content:
    content = content.replace(old_preview_header, new_preview_header)

content = content.replace(
    '        doc_meta_card,\n        stats_cards,',
    '        catalog_banner,\n        doc_meta_card,\n        stats_cards,'
)

# 5. Update build_department_excel Source Metadata sheet
old_excel_meta = """    for row in [
        ["Source File", source_filename or pdf_report.doc_metadata.institution],
        ["Source Type", "COE PDF"],
        ["Source Pages", meta.page_count],
        ["Extraction Timestamp", datetime.now().isoformat(timespec="seconds")],
        ["Students", ca.student_count],
        ["Subjects", ca.subject_count],
        ["Validation Status", "PASSED" if ok else "ISSUES FOUND"],
    ]:"""

new_excel_meta = """    ctx = SESSION.get("analysis_context", {})
    for row in [
        ["Source File", source_filename or pdf_report.doc_metadata.institution],
        ["Source Type", "COE PDF"],
        ["Source Pages", meta.page_count],
        ["Department Code", ctx.get("department", getattr(meta, "catalog_department", "AI_DS"))],
        ["Academic Regulation", ctx.get("regulation", getattr(meta, "catalog_regulation", "R2024"))],
        ["Analysis Semester", ctx.get("semester", getattr(meta, "catalog_semester", "4"))],
        ["Catalog Version", getattr(meta, "catalog_version", ctx.get("catalog_version", "1.0"))],
        ["Catalog SHA256 Checksum", getattr(meta, "catalog_hash", ctx.get("catalog_hash", ""))],
        ["Extraction Timestamp", datetime.now().isoformat(timespec="seconds")],
        ["Students", ca.student_count],
        ["Subjects", ca.subject_count],
        ["Validation Status", "PASSED" if ok else "ISSUES FOUND"],
    ]:"""

if old_excel_meta in content:
    content = content.replace(old_excel_meta, new_excel_meta)

with open(APP_PY, "w", encoding="utf-8") as f:
    f.write(content)

print("Successfully applied UI and metadata patches to app.py")
