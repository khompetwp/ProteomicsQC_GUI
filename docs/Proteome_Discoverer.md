# Proteome Discoverer — ProteomicsQC 0.5.0

เลือก Data source เป็น Proteome Discoverer และ Data level เป็น Identification

1. File: เลือก `.mzid` หนึ่งไฟล์ หรือ Folder: ค้นหา `.mzid` ในโฟลเดอร์/โฟลเดอร์ย่อย
2. ถ้ามีเฉพาะ `.mzid` ให้เอาติ๊ก Create PMultiQC HTML report ออก เพื่อสร้าง Excel
3. ถ้าจะสร้าง HTML ให้วาง `sample.mzid` กับ `sample.mzML` ในโฟลเดอร์เดียวกัน
   รองรับ `sample.mgf` เมื่อไม่มี mzML แต่การทดสอบร่วมของรุ่นนี้ใช้ mzML
4. เลือก Output folder และตั้ง Report folder name ใหม่ แล้วกด Run QC

## วิธีนับใน Excel

- `psm_items`: ทุก SpectrumIdentificationItem รวม alternative ranks, failed threshold และ decoy
- `rank1_passing_items`: เฉพาะ rank 1 และ passThreshold=true โดยไม่คำนวณ FDR ใหม่
- `spectra_with_items`: จำนวน spectrum IDs ที่มีผลค้นหา ไม่ใช่จำนวน MS2 ทั้งหมด
- `unique_peptide_sequences`: ลำดับไม่ซ้ำ ไม่แยก modification
- `referenced_protein_accessions`: accession ที่ถูกอ้างอิง ไม่ใช่ inferred protein groups
- รายงานจำนวน failed-threshold items และ items ที่มี decoy evidence แยกให้เห็น
- RT median ใช้เฉพาะรายการที่ระบุหน่วยวินาที/นาทีชัดเจน ไม่เดาหน่วย RT ของ PD
- Mass error ใช้ experimental/calculated m/z ที่เป็นค่าจำกัดและมากกว่าศูนย์

## ขอบเขตและข้อจำกัด

HTML ใช้เฉพาะ mzid ที่เลือก/ค้นพบและสเปกตรัมที่จับคู่ ชื่อฐานต้องตรงกัน
และต้องเป็น run เดียวกันจริง โปรแกรมไม่คัดลอกสเปกตรัมขนาดใหญ่
โหมด HTML รองรับหนึ่ง run ต่อ mzid และชื่อฐานต้องไม่ซ้ำข้ามโฟลเดอร์
หากพบทั้ง mzML และ MGF จะเลือก mzML

หาก HTML ไม่สำเร็จ Excel จะยังอยู่ โดยสถานะเป็น partial พร้อม processing.log
PMultiQC ใช้กฎกรองของตัวเองจึงอาจนับต่างจาก Excel
การตรวจเบื้องต้นดู XML root และชื่อคู่ไฟล์ ไม่ใช่การยืนยัน XML ทั้งไฟล์หรือคุณภาพทางวิทยาศาสตร์

ยังไม่อ่าน `.pdResult` หรือตาราง LFQ/TMT abundance ของ PD
ยังไม่ได้ทดสอบ mzML จริงขนาด 2 GB; PMultiQC โหลดข้อมูลเข้า RAM และอาจใช้หน่วยความจำมากกว่าขนาดไฟล์
head ของ mzML ใช้แทนไฟล์เต็มเพื่อสร้าง QC ไม่ได้

## ตัวอย่างในแพ็กเกจ

`Examples/SYNTHETIC_ONLY/proteome_discoverer` มีคู่ mzid/mzML ที่สร้างจำลอง
มี 12 MS1, 36 MS2 และ 24 identification items ทั้งหมดเป็นข้อมูลสังเคราะห์
ไม่ใช่ผลทดลองหรือไฟล์ที่ PD สร้างจริง ใช้ทดสอบการอ่านและหน้ารายงานเท่านั้น

ทดสอบรุ่นนี้ด้วย PMultiQC 0.0.48 / MultiQC 1.35:
คู่จำลองสร้าง Excel/HTML ได้; ไฟล์ PD 3.2 จริงทดสอบ Excel ได้
การใช้ไฟล์จริงที่ไม่มีสเปกตรัมจะแสดง HTML partial และเก็บ Excel

คู่มือ PDF 0.4.0 ที่รวมในแพ็กเกจใช้อ้างอิงหน้าจอพื้นฐาน
เอกสารฉบับนี้อธิบายส่วนที่เพิ่มใน 0.5.0
