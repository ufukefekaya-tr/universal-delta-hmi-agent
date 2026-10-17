# Mevcut nesnenin giriş izni

Kaynakla pinlenmiş B10 model2953863504 / serialized4.00.07.04 graph içindeki mevcut, kilidi kapalı nesneye saklanan izin bağı eklenir. Kabul yalnız native kayıt ve dosya bütünlüğü içindir. Vendor/runtime/native piksel/panel, kalite/maximum-age/AND, continuous/safety ve numeric commit-time kabulü açık kalır.

İki proje girdisi gerekir: kaynak driver'ına bağlı kayıtlı adres namespace'i ve insanın projeye ait komut sınıflandırması. Tip/başlıktan START çıkarılmaz. Type1/Sub1 SetOn açıkça `start_request`, Type6/Sub1 mevcut INT/UINT WORD F0 giriş `parameter_write` olmalıdır. STOP, bırakma, acil/safety, momentary, maintained, SetOff ve belirtilmemiş görevler reddedilir. Dosyada `authority: human_project_contract` yazması gerçek insan yetkisini kanıtlamaz; proje sahibinin kararı ve native aday için ayrıca doğrudan insan plan onayı gerekir.

```powershell
.venv/Scripts/python.exe scripts/qualify_existing_edit.py --workspace projects/ornek --source inputs/source.dps --output-dir calibration/R003 --source-reference "Kaynak kaydı" --review-reference "Bağımsız inceleme" --integer-numeric --entry-permission --permission-namespace contracts/namespace.json --action-contract contracts/actions.json
```

Helper dört JSON verir; native çıktı oluşturmaz. Profil `existing_edit_permission_v1` olur; eski plain/numeric profiller değişmez. İki girdi workspace-relative yollardan okunur. Bütün raw byte SHA'ları profile/witness/session'a bağlıdır; whitespace değişikliği de eski onayı geçersiz kılar. Source/profile/witness/static kitaplar/PNG/raw girdiler transaction evrelerinde ve kayıt sonrasında kontrol edilir.

Action JSON'un exact kökü `contract_version:1`, `mode:"existing_entry_action_classification_v1"`, `source_sha256`, `address_namespace_sha256`, `actions` taşır. Her action şu exact alanları içerir:

```json
{"screen_id":"12","element_id":"61","owner_sha256":"<original owner SHA256>","type":1,"subtype":1,"write_address":"{Link2}0@M0","write_link":1,"write_mem_type":0,"mem_len":0,"mem_fmt":2,"action_class":"start_request","gating_authorization":{"authorized":true,"authority":"human_project_contract","reference":"Doğrulanmış proje kararı"}}
```

Örnek ID/adres başka projeye kopyalanmaz. Native sayısal alanlar original owner/binding ile exact eşleşir. BOOL MemLen0/MemFmt2 temsili korunur. `action_classification_sha256` complete action entry'nin `json.dumps(action,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('utf-8')` byte SHA256'sıdır. Bütün action dosyasının raw SHA'sı ayrıdır. Duplicate/unknown alan, float/bool sayısal alan ve yanlış pin reddedilir.

IR `native_entry_permission`, boş text, original native_id/source_owner_sha256/geometri ve `presentation:{}` taşır. `native_integer_numeric` üzerinde izin payload'ı opsiyoneldir; eski `native_presentation` üzerine eklenmez:

```json
{"permission_address":"{Link2}0@X7","enable_level":1,"action_classification_sha256":"<complete action entry SHA256>"}
```

Permission aynı source driver/kanal/istasyonda kayıtlı external BOOL Read olmalıdır. Driver'ın radix, alan ve sınırları kontrol edilir. Komutun original WriteVar'ı uygun BOOL/WORD register'da writable olmalıdır. Textual `{Link2}` numarası native link değildir. Original `InterLockLink = native_index + 1` korunur; nativeLink1 ile textualLink2 doğru olabilir.

Yalnız InterLockVar ve InterLockLevel değişir. Storage, read/write, link, offset/visibility/trigger/macro/keypad/confirmation ve kaynaklar korunur. Kaynak aktif conditional/dynamic işlem veya identity dışı ölçek taşıyorsa reddedilir. Type6 schema'sında ConFirmWindow bulunmaz; uydurulmaz. Numeric original-disabled guard değişmez: işlemler aynı immutable original üzerinde ayrı doğrulanır, ayrık record aralıkları birleşir. Aktif kilitli saved candidate numeric için yeni original sayılmaz.

Static tüketici incelemesi butona giriş/tuş takımını açma aşamasındaki izin kontrolünü gösterir; commit anında tekrar okuma, sample age veya atomic çalışma garantisi vermez. Preview **UNKNOWN · NATIVE NOT RENDERED** kalır; level canlı izin simülasyonu değildir. Kalite/zaman aşımı üreticisi ayrıca qualify edilmeden tam batch hazır sayılmaz.

Opcode `set_existing_entry_permission` original owner pinini, adresi, enable_level0/1 ve action SHA'sını taşır. Saved native, bağımsız IR/original record beklentisiyle karşılaştırılır. Değişen aralıkları tersine koyma complete original BODY'yi eşit vermelidir. [Workflow](WORKFLOW.md), [goals](GOALS.md) ve [doğrulama](../reports/VERIFICATION.md) kabul sınırlarını gösterir.
