"""Generates docs/defense2_slides.pdf (the 2 slides required for Defense 2).

    pip install reportlab
    python docs/build_slides.py

EDIT the two blocks below before submitting:
  * NOT_WORKING  - be HONEST: everything you cannot demo must be listed (a feature listed as working that is
                   broken during the demo costs -2). Remove the "verify" lines once you have tested them.
  * TEAM         - real names. Only list Defense 2 tasks.
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "defense2_slides.pdf")
TEAM_NAME = "DSP Stroke Prediction - Defense 2"

# ---------------------------------------------------------------------------------------------- EDIT ME
NOT_WORKING = [
    ("Drift-triggered retraining (bonus)",
     "Not implemented. Retraining is scheduled (every 10 min) and gated on the number of new good_data files."),
    ("Real ground-truth labels",
     "Simulated: labels of ingested rows are looked up in the labelled reference dataset "
     "(ingested files carry no label by design)."),
    ("[VERIFY BEFORE SUBMITTING] anything that failed in your own end-to-end run",
     "Replace this line: list every feature that does not work on `main` (e.g. Grafana alert delivery to Teams, a "
     "dashboard panel, a DAG task). If everything works, delete this row and write: 'None known'."),
]

TEAM = [
    ("[Person A]", "Model registry and serving",
     "MLflow service + bootstrap (baseline champion), model loading from models:/stroke_model@champion, "
     "POST /reload-model, GET /model-info, thread-safe model holder, custom Airflow image, compose wiring"),
    ("[Person B]", "Training pipeline",
     "training_dag (load_data, train_model, save_training_stats, evaluate_candidate, promote_to_champion, "
     "notify_api_reload, archive_data), promotion rule, fixed test set, training_stats table and drift baseline"),
    ("[Person C]", "Monitoring (Grafana)",
     "Data-quality dashboard, drift and prediction dashboard, 6 alert rules, Teams contact points and routing, "
     "provisioning as code, SQL tests, traffic simulator used to populate the dashboards"),
    ("[Person D]", "Data Docs, alerts, CI/CD",
     "nginx serving Data Docs + report links, two Teams channels (Adaptive Cards), CI extension, CD release workflow "
     "(semantic versioning), demo files, README and documentation"),
]
# -------------------------------------------------------------------------------------------------------

NAVY, GREY, RED, GREEN = colors.HexColor("#1f2a44"), colors.HexColor("#5b6475"), colors.HexColor("#b3261e"), \
    colors.HexColor("#1b7f3b")
TITLE = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=26, textColor=NAVY, leading=30, spaceAfter=4)
SUB = ParagraphStyle("s", fontName="Helvetica", fontSize=13, textColor=GREY, leading=16, spaceAfter=14)
CELL = ParagraphStyle("c", fontName="Helvetica", fontSize=12, leading=15)
CELLB = ParagraphStyle("cb", parent=CELL, fontName="Helvetica-Bold")
HEAD = ParagraphStyle("h", parent=CELLB, textColor=colors.white)


def table(rows, widths, header, accent):
    data = [[Paragraph(h, HEAD) for h in header]]
    for row in rows:
        data.append([Paragraph(cell, CELLB if i == 0 else CELL) for i, cell in enumerate(row)])
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), accent),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f5f9")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#d5d9e2")),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def main():
    doc = SimpleDocTemplate(OUT, pagesize=landscape(A4), leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.2 * cm, title=TEAM_NAME,
                            author="DSP team")
    width = landscape(A4)[0] - 3.6 * cm
    story = [
        Paragraph("Features not working / not implemented", TITLE),
        Paragraph(f"{TEAM_NAME} - everything not listed here is demoed from the main branch", SUB),
        table(NOT_WORKING, [width * 0.33, width * 0.67], ["Feature", "Status"], RED),
        PageBreak(),
        Paragraph("Who did what (Defense 2)", TITLE),
        Paragraph("Each member answers questions about the features listed in their row", SUB),
        table(TEAM, [width * 0.13, width * 0.2, width * 0.67], ["Member", "Workstream", "Tasks"], GREEN),
    ]
    doc.build(story)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
