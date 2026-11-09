# ProteomicsQC GUI

Python desktop application for quality control of FragPipe TSV results, featuring per-run QC metrics,
Excel summaries with analysis history, and optional PMultiQC HTML reports.

โปรแกรมเดสก์ท็อปสำหรับสรุป QC ของตาราง FragPipe รุ่น 0.2.0

## ดาวน์โหลดจาก GitHub

เปิด [ProteomicsQC_GUI](https://github.com/khompetsh2-cloud/ProteomicsQC_GUI) แล้วเลือก **Code → Download ZIP** และแตกไฟล์
หาก repository เป็น Private ต้องเข้าสู่ระบบด้วยบัญชีที่มีสิทธิ์เข้าถึงก่อน

หรือใช้ Git:

```powershell
git clone https://github.com/khompetsh2-cloud/ProteomicsQC_GUI.git
cd ProteomicsQC_GUI
```

Repository เก็บโค้ดและคู่มือ ส่วนข้อมูลทดลองและผลลัพธ์เก็บไว้ในเครื่องที่ใช้งาน
ไฟล์ `.gitignore` ข้ามข้อมูลทดลอง ผลลัพธ์ สภาพแวดล้อม Python และไฟล์สำรอง

## ติดตั้งบนคอม Windows เครื่องอื่น

นำ `msqc_gui.py`, `msqc2.py`, `requirements.txt` และคู่มือนี้ไปไว้ในโฟลเดอร์เดียวกัน
ติดตั้ง Python 3.13 พร้อม Tcl/Tk แล้วเปิด PowerShell ในโฟลเดอร์โปรแกรม:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe msqc_gui.py
```

ครั้งถัดไปเปิดด้วยคำสั่งสุดท้ายได้เลย ไม่ต้องติดตั้งใหม่ทุกรอบ

สร้าง `.venv` ใหม่ในเครื่องปลายทาง ไม่ต้องคัดลอก `.venv` จากเครื่องเดิม
ติดตั้งครั้งแรกต้องเข้าถึงแหล่งแพ็กเกจ Python ที่องค์กรอนุญาต
`requirements.txt` ระบุเวอร์ชัน dependencies หลักที่ใช้ทดสอบ ไม่ใช่ lockfile ของ dependencies ทุกตัว
ไม่ต้องมี Microsoft Excel เพื่อสร้างไฟล์; เปิดผลได้ด้วยโปรแกรมที่รองรับ `.xlsx`

## วิธีใช้งาน

1. เลือกไฟล์ `psm.tsv` หรือโฟลเดอร์เพื่อค้นหา `psm.tsv` ในโฟลเดอร์ย่อย (โหมด PSM)
2. สำหรับ Peptide/Protein ให้เลือก TSV ทีละไฟล์และเลือก Data level ให้ตรง
3. เลือกโฟลเดอร์ผลลัพธ์ที่เขียนได้; ปล่อยว่างจะใช้ `ResultQC` ใกล้ input
4. ติ๊ก Create PMultiQC HTML report หากต้องการ HTML (PSM เท่านั้น)
5. กด Run QC แล้วเปิด Excel หรือ HTML จากปุ่มในโปรแกรม

แต่ละรอบสร้างโฟลเดอร์ใหม่ `qc_YYYYMMDD_HHMMSS_...` ชั้นเดียว:

```text
qc_.../
  QC_summary.xlsx
  multiqc_report.html     เมื่อขอสร้าง HTML และสร้างสำเร็จ
  _support/               ข้อมูลประกอบของ PMultiQC เมื่อสร้างรายงาน
  processing.log          เฉพาะเมื่อ QC หรือการสร้าง HTML มีปัญหา
```

ไม่สร้าง CSV และ JSON แยกตามตารางอีกแล้ว ไฟล์ผลเก่าจะไม่ถูกลบหรือแปลงอัตโนมัติ
เก็บ `_support` ไว้คู่กับรายงาน โดยเฉพาะเมื่อต้องย้ายทั้งชุดผลลัพธ์

## สิ่งที่อยู่ใน Excel

- Summary: ผลสรุปต่อไฟล์
- By run: ผลสรุปต่อ Spectrum File; ถ้าไม่มีคอลัมน์นี้ใช้ชื่อโฟลเดอร์แทน
- Numeric audit: ค่าตัวเลขที่ถูกต้อง ขาดหาย หรือผิดรูปแบบ
- Missing values: ค่าว่างต่อคอลัมน์
- Input files: รายชื่อ input ขนาดไฟล์ เวลาแก้ไข และระบุว่าใช้คำนวณ QC หรืออยู่ในขอบเขตสแกน PMultiQC
- Run info: เวลาเริ่ม/จบ สถานะ เวอร์ชัน Python/แพ็กเกจ การตั้งค่า และคำสั่ง PMultiQC

แท็บที่ไม่เกี่ยวกับโหมดที่เลือกจะว่าง ตารางใน GUI แสดงได้ไม่เกิน 1,000 แถวต่อแท็บ แต่ Excel เก็บผลสรุปทั้งหมด
จำนวน peptide ที่ไม่ซ้ำเป็นค่าต่อไฟล์/ต่อ run; ไม่ควรนำมาบวกแล้วเรียกว่า unique peptide รวมทุกไฟล์

## ขอบเขตข้อมูลและการประมวลผล

GUI QC ไม่เขียนทับไฟล์ต้นฉบับ ไม่กรอง FDR ไม่ตัด decoy/contaminant ไม่ลบแถวซ้ำ และไม่เติมค่าว่าง
อ่านทุกค่าเป็นข้อความ ตัดช่องว่างหัวท้าย และนับข้อความว่างเป็นข้อมูลขาด โดยเก็บ `NA` เป็นข้อความตามเดิมทุกโหมด
การคำนวณตัวเลขไม่นำค่าที่แปลงไม่ได้หรือ infinity มาคำนวณ แต่ยังนับแถวนั้นในจำนวนแถวทั้งหมด
Mass error ใช้คู่ m/z ที่เป็นตัวเลขจำกัดและมากกว่าศูนย์ แล้วคำนวณ `1e6 * (observed - calculated) / calculated`

PMultiQC อ่านไฟล์ต้นฉบับทั้งโฟลเดอร์ที่เลือก; ถ้าเลือกไฟล์เดียวจะอ่านทั้งโฟลเดอร์ที่ไฟล์นั้นอยู่
จึงอาจเห็นไฟล์มากกว่าส่วน QC ของ GUI และใช้กฎการอ่าน/คำนวณของ PMultiQC เอง
รายชื่อใน Input files เป็นรายการไฟล์ในขอบเขตที่สแกน ไม่ได้ยืนยันว่า PMultiQC อ่านทุกไฟล์นั้นจริง
โปรแกรมข้ามโฟลเดอร์ผลลัพธ์ของรอบนี้ และโฟลเดอร์ผลของโปรแกรมรุ่นนี้ที่ตรวจพบ เพื่อหลีกเลี่ยงการอ่านรายงานเก่าซ้ำ
เก็บข้อมูล input ให้คงที่ระหว่างรัน; ประวัติเก็บ path/size/mtime โดยไม่ได้ทำสำเนาหรือ checksum ของข้อมูล
ปิดการตรวจเวอร์ชันออนไลน์และการสรุปด้วย AI ในคำสั่ง PMultiQC ของโปรแกรม

ถ้า HTML สร้างไม่สำเร็จ ผล QC ใน Excel ยังอยู่ และ Run info จะแสดงสถานะ partial พร้อมรายละเอียดใน processing.log
หาก input ผิดรูปแบบ สถานะจะเป็น failed; อย่าใช้แถวว่างใน Excel เป็นผลว่าไม่พบ PSM
Excel เป็นผลสรุป ไม่ได้คัดลอก PSM ทั้งหมดเข้าไป

## ข้อจำกัดและการทดสอบก่อนใช้ประจำ

ยังอ่าน TSV ทีละไฟล์ทั้งไฟล์เข้า RAM และไม่มีปุ่มยกเลิกงาน จึงควรทดสอบขนาดข้อมูลจริงกับเครื่องทำงาน
ควรเลือกโฟลเดอร์ input เฉพาะชุดทดลองเพื่อให้ขอบเขต PMultiQC ชัดเจน
โปรแกรมไม่ได้ประเมิน QC ของเครื่อง MS จาก RAW และไม่ได้ตัดสินผ่าน/ไม่ผ่านอัตโนมัติ
ตัว GUI ใช้การเปิดโฟลเดอร์/Excel ของ Windows; หากจะใช้ระบบอื่นต้องปรับส่วนนี้

## เรียกผ่านคำสั่ง

```powershell
.\.venv\Scripts\python.exe msqc2.py --input data --output results --skip-multiqc
.\.venv\Scripts\python.exe msqc2.py --input data --output results
.\.venv\Scripts\python.exe msqc2.py --input peptide.tsv --level Peptide --output results --skip-multiqc
```

รหัสจบการทำงาน: 0 = สำเร็จ, 1 = QC สำเร็จแต่ HTML มีปัญหา, 2 = QC/การบันทึกผลล้มเหลว

## อัปเดตโปรแกรม

ถ้าดาวน์โหลดด้วย Git ให้ปิดโปรแกรมก่อน แล้วรันในโฟลเดอร์ repository:

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

ถ้าดาวน์โหลดด้วย ZIP ให้ดาวน์โหลดรุ่นใหม่และแตกลงโฟลเดอร์ใหม่ แล้วทำขั้นตอนติดตั้ง
เก็บข้อมูลทดลองและผลลัพธ์เดิมไว้แยกจากโฟลเดอร์โปรแกรมเพื่อย้ายรุ่นได้สะดวก

## การทดสอบรุ่นเริ่มต้น

ทดสอบ integration 8 กรณี ครอบคลุมการส่งออก Excel โหมด PSM/Peptide/Protein การเก็บ `NA`
การแยกผลตาม run ประวัติข้อผิดพลาด และการแสดงผลใน GUI
ทดสอบเส้นทาง GUI → QC engine → PMultiQC กับไฟล์ที่มี 600 PSM โดยตัวเลขสรุปตรงกับโค้ดก่อนปรับ
ยังต้องทดสอบกับขนาดข้อมูลจริงและสภาพแวดล้อมของเครื่องปลายทาง

รุ่นนี้รันผ่าน Python; ยังไม่ได้จัดแพ็กเป็น `.exe`
