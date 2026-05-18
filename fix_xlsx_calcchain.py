"""Repair RANKINGS_SUMMARY.xlsx after the scripted rebuild.

Two problems, both caused by the workbook having been Excel-saved before the
rebuild/chart/insight scripts rewrote whole sheets and added hundreds of new
formula cells:

1. Stale calcChain.xml — records the OLD formula calculation order; a mismatch
   triggers Excel's "We found a problem with some content" repair prompt.
   Fix: remove calcChain.xml (Excel rebuilds it on open) plus its
   [Content_Types].xml override and workbook.xml.rels relationship.

2. Stale cached formula values — every formula cell still carries the <v>
   value Excel cached *before* the rewrite. Most visibly, the model sheet's
   RANK cells were flipped from ascending to descending but still show the old
   cached number until something forces a recalc — so ranks appear to "change
   when you click on them." Fix: set calcPr fullCalcOnLoad="1" so Excel
   recalculates everything on open and the cached values never get shown.
"""
import os
import re
import shutil
import zipfile

XLSX = "RANKINGS_SUMMARY.xlsx"
BACKUP = "RANKINGS_SUMMARY.bak4_precalcfix.xlsx"

CALC_PART = "xl/calcChain.xml"


def main():
    if not os.path.exists(BACKUP):
        shutil.copy2(XLSX, BACKUP)

    with zipfile.ZipFile(XLSX, "r") as zin:
        names = zin.namelist()
        items = {n: zin.read(n) for n in names}

    # 1. drop calcChain.xml + its content-type override + its workbook rel.
    #    Idempotent: cleans the override/rel even if the part is already gone
    #    (a previous partial run may have removed only the part).
    if CALC_PART in items:
        del items[CALC_PART]
        print("Removed calcChain.xml.")
    else:
        print("calcChain.xml already absent.")

    ct = items["[Content_Types].xml"].decode("utf-8")
    n_ct = ct.count("calcChain")
    ct = re.sub(r'<Override PartName="/xl/calcChain\.xml"[^>]*?/>', "", ct)
    items["[Content_Types].xml"] = ct.encode("utf-8")

    rels_path = "xl/_rels/workbook.xml.rels"
    rels = items[rels_path].decode("utf-8")
    n_rels = rels.count("calcChain")
    rels = re.sub(r'<Relationship[^>]*?calcChain\.xml"[^>]*?/>', "", rels)
    items[rels_path] = rels.encode("utf-8")
    print(f"Cleaned calcChain refs: content-types {n_ct}->0, "
          f"workbook rels {n_rels}->0.")

    # 2. force full recalculation on open so stale cached <v> values
    #    (esp. the old ascending RANK numbers) are never displayed
    wbk = items["xl/workbook.xml"].decode("utf-8")
    if "<calcPr" in wbk:
        # ensure fullCalcOnLoad="1" is present on the existing calcPr element
        def _patch(m):
            tag = m.group(0)
            if "fullCalcOnLoad" in tag:
                tag = re.sub(r'fullCalcOnLoad="[^"]*"',
                             'fullCalcOnLoad="1"', tag)
            else:
                tag = tag[:-2] + ' fullCalcOnLoad="1"/>'
            return tag
        wbk = re.sub(r'<calcPr[^>]*?/>', _patch, wbk)
    else:
        # insert a calcPr right before </workbook>
        wbk = wbk.replace(
            "</workbook>",
            '<calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>',
        )
    items["xl/workbook.xml"] = wbk.encode("utf-8")
    print("Set calcPr fullCalcOnLoad=\"1\".")

    # rewrite the archive
    with zipfile.ZipFile(XLSX, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in items.items():
            zout.writestr(name, data)

    print(f"Repackaged {XLSX}.")


if __name__ == "__main__":
    main()
