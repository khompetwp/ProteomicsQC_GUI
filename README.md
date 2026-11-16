# ProteomicsQC GUI

โปรแกรม QC บน Windows สำหรับสรุปตารางผลจาก **FragPipe, DIA-NN, MaxQuant และ Proteome Discoverer** เป็น Excel และเลือกสร้างรายงาน HTML ด้วย PMultiQC ได้

เวอร์ชัน `0.5.0` รองรับ Windows 10/11 x64 โปรแกรมอ่านผลวิเคราะห์ที่มีอยู่แล้วและ **ไม่ได้ค้นหา peptide/protein จาก RAW data เอง**

## รองรับข้อมูลอะไรบ้าง

| Data source | Input หลัก | สิ่งที่สรุป |
|---|---|---|
| FragPipe | PSM TSV ชื่อใดก็ได้ หรือโฟลเดอร์ที่มี `psm*.tsv`; Peptide/Protein ใช้ TSV ทีละไฟล์ | PSM, peptide และ protein identifiers ตามโหมด |
| DIA-NN | main report `.parquet` หรือ `.tsv` | precursor observations ต่อ run, unique precursors, peptide sequences และ protein-group strings |
| MaxQuant | โฟลเดอร์ `txt` ที่มี `evidence.txt`, `msms.txt`, `proteinGroups.txt` | evidence features, MS/MS PSM rows และ protein-group rows |
| Proteome Discoverer | `.mzid` หรือโฟลเดอร์ที่มี `.mzid`; HTML ต้องมี `.mzML`/`.mgf` ชื่อฐานเดียวกัน | identification items ทุก rank/threshold, rank 1 ที่ผ่านเกณฑ์ และ referenced protein accessions |

Proteome Discoverer รองรับ identification จาก `.mzid` แต่ยังไม่อ่าน `.pdResult` หรือตาราง abundance ของ PD ดูรายละเอียดที่ [docs/Proteome_Discoverer.md](docs/Proteome_Discoverer.md)

## วิธีใช้

1. เลือก **Data source**, input และ Data level ให้ตรงกับโปรแกรมต้นทาง
2. เลือก Output parent folder และตั้ง Report folder name หรือปล่อยว่างเพื่อสร้างชื่ออัตโนมัติ
3. เลือก **Create PMultiQC HTML report** หากต้องการ HTML
4. กด **Run QC** แล้วเปิด Excel, HTML หรือ results folder จากโปรแกรม

ชื่อโฟลเดอร์ผลลัพธ์ซ้ำจะถูกปฏิเสธ โปรแกรมไม่เขียนทับงานเดิม การกด Cancel จะรอการอ่านตารางปัจจุบันจบ แต่สามารถหยุด subprocess ที่สร้าง HTML ระหว่างรันได้

### Portable และตัวติดตั้ง

- Portable: แตก ZIP ทั้งหมดแล้วเปิด `ProteomicsQC.exe`; ต้องเก็บ `_internal` ไว้ข้างกัน
- Setup: ติดตั้งสำหรับผู้ใช้ปัจจุบัน สร้าง Start menu และเลือก desktop shortcut ได้
- ไม่ต้องติดตั้ง Python หรือแก้ PATH เพราะแพ็กเกจมี private Python 3.13 และ dependencies
- EXE/Setup ยังไม่ได้เซ็นดิจิทัล จึงอาจแสดง `Unknown publisher`
- ตัวอย่างใน `Examples/SYNTHETIC_ONLY` เป็นข้อมูลจำลอง ไม่ใช่ผลทดลอง

## ผลลัพธ์

```text
qc_วันเวลา_รหัส/
  QC_summary.xlsx
  multiqc_report.html     เมื่อเลือกสร้างและรายงานสำเร็จ
  _support/               ข้อมูลประกอบ PMultiQC
  processing.log          เมื่อมีปัญหา รายงานไม่ครบ หรือยกเลิก
```

Excel มีชีต Summary, By run, Numeric audit, Missing values, Input files และ Run info พร้อมเวอร์ชัน dependency, input scope, คำสั่งและสถานะการประมวลผล GUI แสดงตัวอย่าง 1,000 แถวแรก แต่ workbook เก็บตารางสรุปทั้งหมด

## หลักการนับและข้อควรระวัง

- ไม่เขียนทับ input และไม่เพิ่มการกรอง q-value/FDR, decoy, contaminant หรือแถวซ้ำ
- ไม่เติม missing values และไม่ renormalise; `NA` แบบข้อความยังเป็นข้อความเดิม
- ค่าตัวเลขผิดรูปแบบหรือ infinity ไม่ใช้ในสถิติตัวเลข แต่แถวยังถูกนับ
- ไม่มีการตัดสิน PASS/FAIL ทางวิทยาศาสตร์โดยอัตโนมัติ
- อย่าบวก unique counts ระหว่าง run/ไฟล์แล้วเรียกว่า unique ของทั้งงาน
- PMultiQC มีกฎกรองและวิธีคำนวณของตัวเอง ตัวเลขใน HTML จึงอาจต่างจาก Excel ซึ่งนับทุกแถวของ input
- หาก HTML ล้มเหลวหรืออ่านได้ไม่ครบ Excel จะยังอยู่ โดยงานมีสถานะ `partial`; ให้ตรวจ Log และ `processing.log`

PMultiQC `0.0.48` มี compatibility shim สำหรับข้อความ categorical ของ DIA-NN และ Protein group IDs แบบตัวเลขของ MaxQuant โดยแก้ชนิดข้อมูลในหน่วยความจำเท่านั้น ไม่เปลี่ยน input หรือเพิ่มตัวกรอง ต้องทดสอบ shim ใหม่เมื่ออัปเกรด PMultiQC

## พัฒนาจาก source

ใช้ Python 3.13 x64 พร้อม Tcl/Tk และดาวน์โหลด repository ทั้งชุด:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe msqc_gui.py
```

ตัวอย่าง CLI:

```powershell
.\.venv\Scripts\python.exe msqc2.py --source FragPipe --input data --output results
.\.venv\Scripts\python.exe msqc2.py --source DIA-NN --input report.parquet --output results
.\.venv\Scripts\python.exe msqc2.py --source MaxQuant --input path_to_txt --output results
.\.venv\Scripts\python.exe msqc2.py --source "Proteome Discoverer" --input sample.mzid --output results
```

เพิ่ม `--skip-multiqc` เพื่อสร้าง Excel เท่านั้น Exit codes: `0` สำเร็จ, `1` Excel สำเร็จแต่ HTML ล้มเหลว/ไม่ครบ, `2` QC ล้มเหลว, `130` ผู้ใช้ยกเลิก

### ทดสอบและ build

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools/generate_synthetic_qc.py --output sample_data/synthetic_qc
.\.venv\Scripts\python.exe tools/build_windows.py
```

ข้อมูล DIA-NN/MaxQuant ใน regression suite เป็น synthetic fixtures และยังต้องยืนยันกับไฟล์จริงหลายเวอร์ชัน การอ่านตารางใช้ RAM ตามขนาดไฟล์ และยังไม่ได้ทดสอบ mzML จริงขนาด 2 GB

## License และโครงการภายนอก

ProteomicsQC เผยแพร่ภายใต้ [GNU GPL version 3 only](LICENSE) ดูวิธีเข้าถึง source ของแต่ละ release ที่ [SOURCE_CODE.md](SOURCE_CODE.md) และรายการ dependency/licensing ที่ [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt)

PMultiQC และ MultiQC เป็นโครงการภายนอก ProteomicsQC เป็นโครงการอิสระและไม่ได้รับการรับรองโดยผู้พัฒนา PMultiQC, MultiQC, FragPipe, DIA-NN, MaxQuant หรือ Proteome Discoverer

