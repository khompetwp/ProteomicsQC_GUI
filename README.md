# ProteomicsQC GUI

Windows desktop QC for FragPipe, DIA-NN, MaxQuant and Proteome Discoverer, with compact Excel summaries and optional PMultiQC HTML reports.

รุ่น 0.5.0 สำหรับ Windows 10/11 x64 — โปรแกรมสรุป QC ของผลวิเคราะห์ ไม่ประมวลผล RAW เพื่อค้นหา peptide/protein เอง

## สิ่งใหม่ใน 0.5.0

- เพิ่ม Data source **Proteome Discoverer**: อ่าน `.mzid` เพื่อสรุป identification ใน Excel
- HTML ใช้ `.mzid` กับคู่ `.mzML` หรือ `.mgf` ชื่อฐานเดียวกันในโฟลเดอร์เดียวกัน
- แยกจำนวน identification items ทุก rank/threshold ออกจาก rank 1 ที่ผ่านเกณฑ์
- ตรวจคู่ไฟล์และเก็บ Excel ไว้เมื่อ HTML ไม่พร้อม มีตัวอย่างจำลอง PD ใน Examples/SYNTHETIC_ONLY
- ยังไม่อ่าน `.pdResult` หรือตาราง Excel abundance ของ PD และยังไม่ทดสอบ mzML จริงขนาด 2 GB
- คู่มือ PDF 0.4.0 อธิบายหน้าจอพื้นฐาน ส่วนที่เพิ่มใหม่ดู `docs/Proteome_Discoverer.md`

## สิ่งใหม่ใน 0.4.0

- GUI แบบตั้งค่าด้านบนและตารางเต็มความกว้าง ใช้ ttkbootstrap และโลโก้ Q ชมพู–ฟ้า
- **Output folder** พร้อมแสดงตำแหน่งรายงานที่จะสร้างจริง
- **Create PMultiQC HTML report** เปิดเป็นค่าเริ่มต้น; FragPipe Peptide/Protein รองรับ Excel เท่านั้น
- ตรวจหัวคอลัมน์แบบไม่อ่านข้อมูลทั้งไฟล์ก่อนรัน ข้อความผ่านการตรวจหัวตารางไม่ใช่การผ่านเกณฑ์คุณภาพทางวิทยาศาสตร์
- ตาราง Summary อ่านง่ายขึ้นและแสดงตัวอย่าง By run 6 run แรก ใช้ค่าจริงจาก workbook โดยไม่เปลี่ยนวิธีนับ
- Help / About เปิดคู่มือ PDF ที่รวมในโปรแกรม; แท็บ Log มีปุ่ม Copy log / error
- จำโฟลเดอร์ล่าสุดไว้ใน `%LOCALAPPDATA%\ProteomicsQC\settings.json` เพียงไฟล์เดียว ไม่เก็บเนื้อหา input และไม่จำการปิด HTML ข้ามการเปิดโปรแกรม
- อัปเกรดโดยปิดโปรแกรมแล้วรัน Setup ใหม่ในตำแหน่งเดิม ไม่ต้องถอนรุ่นเดิม ผล QC ควรเก็บนอกโฟลเดอร์ติดตั้ง

## ใช้ชุด portable โดยไม่ติดตั้ง

แตก ZIP ทั้งหมด แล้วเปิด `ProteomicsQC.exe` โดยเก็บ `_internal` ไว้ข้างกัน ไม่ต้องติดตั้ง Python หรือแก้ PATH
มี private Python 3.13 และ dependencies ของโปรแกรมรวมอยู่แล้ว ตัว launcher ใช้ .NET Framework 4.x ของ Windows
ตัวอย่างใน `Examples/SYNTHETIC_ONLY` เป็นข้อมูลจำลองเท่านั้น

หากใช้ Setup.exe จะติดตั้งสำหรับผู้ใช้ปัจจุบัน สร้างรายการ Start menu และเลือกสร้าง desktop shortcut ได้
ถอนการติดตั้งได้ผ่าน Windows Apps โปรแกรมไม่ลบข้อมูลทดลองหรือรายงานที่บันทึกไว้นอกโฟลเดอร์โปรแกรม
ตัวติดตั้งและ EXE ยังไม่ได้เซ็นดิจิทัล จึงอาจแสดง Unknown publisher

## วิธีใช้งาน

1. เลือก **Data source** ให้ตรงกับโปรแกรมต้นทาง
2. เลือกไฟล์หรือโฟลเดอร์ผลวิเคราะห์ และ Data level
3. เลือก Output parent folder ที่เขียนได้; ปล่อยว่างใช้ ResultQC ใกล้ input แล้วตั้ง Report folder name ได้ เช่น `HeLa QC รอบสอง`; เว้นชื่อว่างใช้ชื่ออัตโนมัติ ชื่อซ้ำจะแจ้งเตือนโดยไม่เขียนทับ
4. ติ๊กสร้าง HTML หากต้องการ แล้วกด Run QC
5. เปิด Excel/HTML จากปุ่มในโปรแกรม หรือกด Cancel เพื่อขอยกเลิก

| Data source | Input | หน่วยที่โปรแกรมนับ |
|---|---|---|
| FragPipe | เลือก PSM TSV ชื่อใดก็ได้ เช่น psm_2.tsv; เลือกโฟลเดอร์จะค้นหา psm*.tsv; peptide/protein TSV ทีละไฟล์ | PSM / peptide / protein identifiers ตามโหมด |
| DIA-NN | main report .parquet หรือ .tsv; เริ่มพัฒนาจากคอลัมน์ 2.2.0 | precursor observations ต่อ run, unique precursors, peptide sequences, protein-group strings |
| MaxQuant | โฟลเดอร์ txt หรือโฟลเดอร์ที่มี txt; ต้องมี evidence.txt, msms.txt, proteinGroups.txt | evidence features, MS/MS PSM rows และ protein-group rows แยกกัน |
| Proteome Discoverer | `.mzid` ทีละไฟล์ หรือโฟลเดอร์ที่มี `.mzid`; HTML ใช้คู่ `.mzML`/`.mgf` ชื่อฐานเดียวกันในโฟลเดอร์เดียวกัน | identification items ทุก rank/threshold; แยกจำนวน rank 1 ที่ผ่านเกณฑ์ และ protein accessions ที่ถูกอ้างอิง |

Proteome Discoverer เพิ่มตั้งแต่รุ่น `0.5.0`
รองรับ Excel สรุป identification จาก `.mzid` และ PMultiQC HTML จากไฟล์สเปกตรัมที่จับคู่
ยังไม่อ่านตาราง Excel abundance ของ PD รายละเอียดอยู่ใน `docs/Proteome_Discoverer.md`

MaxQuant จะอ่าน summary.txt, parameters.txt และ msmsScans.txt เพิ่มเมื่อมี
DIA-NN ต้องเป็น main report ไม่ใช่ pg_matrix, spectral library หรือ site report; หากมีหลาย main report ให้เลือกไฟล์โดยตรง
เวอร์ชัน MaxQuant เป้าหมายยังไม่ทราบ ต้องยืนยันอีกครั้งกับไฟล์จริง

## ผลลัพธ์ต่อรอบ

```text
qc_วันเวลา_รหัส/
  QC_summary.xlsx
  multiqc_report.html     เมื่อเลือกสร้างและรายงานสำเร็จ
  _support/               ข้อมูลประกอบ PMultiQC รวม mzQC เมื่อ plugin สร้าง
  processing.log          เมื่อมีปัญหา รายงานไม่ครบ หรือยกเลิก
```

Excel มี Summary, By run, Numeric audit, Missing values, Input files และ Run info
รวมประวัติ เวลา เวอร์ชัน dependencies ขอบเขต input คำสั่งที่ใช้ และสถานะใน Run info
GUI แสดง 1,000 แถวแรกต่อแท็บ แต่ Excel เก็บตารางสรุปทั้งหมด
จำนวน unique ต่อ run/ไฟล์ไม่ควรนำมาบวกแล้วเรียกว่า unique ของทั้งงาน

## ไม่มีการกรองเพิ่มเติมของโปรแกรม

โปรแกรมไม่เขียนทับ input ไม่กรอง q-value/FDR ไม่ตัด decoy/contaminant ไม่ลบแถวซ้ำ ไม่เติมค่าว่าง และไม่ renormalise
ข้อความ NA เป็นข้อความตามเดิม; ช่องว่างถือเป็น missing; ค่าตัวเลขผิดรูปแบบ/infinity ไม่ใช้ในสถิติตัวเลขแต่ยังนับแถวนั้น
ไฟล์ต้นทางอาจผ่านการกรองหรือ normalization มาแล้วตามการตั้งค่าของ FragPipe/DIA-NN/MaxQuant
ไม่มีการตัดสิน PASS/FAIL อัตโนมัติ

**PMultiQC มีวิธีคำนวณและการกรองภายในของมันเอง** เช่น ตัด decoy/reverse และแยก transferred evidence ตามกราฟ
จึงอาจมีตัวเลขต่างจาก Excel ซึ่งนับทุกแถวของ input โปรแกรมตรวจว่ารายงานมี plot data และตรวจข้อความ plugin ล้มเหลว
หากสร้าง HTML ได้แต่บางส่วนอ่านไม่สำเร็จจะรายงาน partial; ควรตรวจ Log ก่อนนำรายงานไปใช้

FragPipe PMultiQC ใช้ PSM ชุดเดียวกับที่เลือก/ค้นพบสำหรับ Excel QC โดยส่ง path ต้นฉบับให้ worker รองรับชื่อไฟล์กำหนดเอง ไม่เปลี่ยนชื่อหรือคัดลอกข้อมูล ส่วนไฟล์ประกอบ เช่น combined_protein.tsv ยังสแกนจากโฟลเดอร์ input
DIA-NN ใช้ main report ที่เลือก ส่วน log/metadata อาจอ่านจากโฟลเดอร์เดียวกัน
MaxQuant ใช้โฟลเดอร์ที่มีชุดตารางที่ตรวจพบ
โฟลเดอร์ผลของโปรแกรมและ _support จะถูกข้ามในการสแกน

### ความเข้ากันได้ PMultiQC 0.0.48

worker มี compatibility shim เฉพาะเวอร์ชันนี้: แปลงคอลัมน์ข้อความ DIA-NN ที่เก็บแบบ categorical และ MaxQuant Protein group IDs แบบตัวเลขเป็นชนิดข้อความในหน่วยความจำ
เพื่อหลีกเลี่ยงข้อผิดพลาดของ plugin ไม่มีการแก้ไฟล์แพ็กเกจ ไม่มีการเปลี่ยนค่า input และไม่เพิ่มตัวกรอง
เมื่ออัปเกรด PMultiQC ต้องทดสอบใหม่ shim ไม่ทำงานกับเวอร์ชันอื่น

## ติดตั้งจาก source เพื่อพัฒนา

ดาวน์โหลด repository ทั้งชุด ไม่ใช่เฉพาะไฟล์ .py สองไฟล์ ใช้ Python 3.13 x64 พร้อม Tcl/Tk

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe msqc_gui.py
```

สร้าง venv ใหม่บนแต่ละเครื่อง requirements.txt pin dependencies หลัก ส่วน portable มีรายการเวอร์ชันทั้งหมดใน _internal/environment.json

```powershell
.\.venv\Scripts\python.exe msqc2.py --source FragPipe --input data --output results
.\.venv\Scripts\python.exe msqc2.py --source FragPipe --input psm_2.tsv --output results --report-name "HeLa QC รอบสอง"
.\.venv\Scripts\python.exe msqc2.py --source DIA-NN --input report.parquet --output results
.\.venv\Scripts\python.exe msqc2.py --source MaxQuant --input path_to_txt --output results
```

เพิ่ม `--skip-multiqc` เพื่อสร้าง Excel เท่านั้น
Exit codes: 0 สำเร็จ, 1 Excel สำเร็จแต่ HTML ล้มเหลว/ไม่ครบ, 2 QC ล้มเหลว, 130 ผู้ใช้ยกเลิก
Cancel จะรอการอ่านตารางปัจจุบันจบก่อน แต่ยกเลิก subprocess สร้างรายงานได้ระหว่างรัน

## สร้าง portable และตัวติดตั้ง

```powershell
.\.venv\Scripts\python.exe tools/generate_synthetic_qc.py --output sample_data/synthetic_qc
.\.venv\Scripts\python.exe tools/build_windows.py
```

builder คัดลอก private CPython/Tcl/Tk และ site-packages จาก venv ที่ใช้ build รวม package metadata, plugin assets และ DLLs
จึงมีขนาดค่อนข้างใหญ่ แต่หลีกเลี่ยงการพึ่ง Python ในเครื่องปลายทาง ไม่เขียนทับโฟลเดอร์ build เดิม
ต้องมี C# compiler ของ .NET Framework สำหรับสร้าง launcher บน Windows
ใช้ Inno Setup compile packaging/ProteomicsQC.iss เพื่อสร้าง Setup.exe จาก portable ที่ทดสอบแล้ว

## ทดสอบและข้อจำกัด

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

ชุด synthetic มี 6 runs และ 678 precursor/evidence rows; ทดสอบข้ามไฟล์ด้วย manifest ไม่ใช่ค่าจากการรัน DIA-NN/MaxQuant จริง
สร้างด้วย tools/generate_synthetic_qc.py จากชื่อคอลัมน์ในเอกสาร DIA-NN ณ วันออก 2.2.0 และตารางมาตรฐาน MaxQuant
ยังต้องตรวจไฟล์จริงของ DIA-NN/MaxQuant และทดสอบบน Windows ที่ไม่มี Python
การอ่านตารางยังใช้ RAM ตามขนาดไฟล์ จึงต้องทดสอบข้อมูลขนาดจริงบนเครื่องปลายทาง

โปรแกรมเก็บประวัติ path/size/mtime ของ input โดยไม่ทำสำเนาและไม่คำนวณ checksum ระหว่างงานปกติ
ข้อมูลทดลองและผล QC ไม่ต้องอัปโหลด GitHub; .gitignore ข้ามข้อมูลและ build outputs

หลังแพ็กแล้วพัฒนาต่อได้: แก้ source → ทดสอบ → build portable/Setup รุ่นใหม่ ไม่แก้ .exe โดยตรง

## Preview 2

Report workers explicitly use UTF-8 so Thai paths and custom report filenames can be validated correctly on Thai Windows locales.
