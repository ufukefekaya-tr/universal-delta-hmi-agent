# Yeni HMI projesi — yeniden kullanılabilir görev promptu

**0.2.0 headless yolu:** [Tek görev başlangıç yetkisi, workflow/goals ve teslim sınırı](../docs/HEADLESS_RELEASE.md). Etkileşimli insan onayı kuralları legacy akışta korunur; headless işte güvenilen başlatıcı policy’si ve exact bağımsız teknik/sıralı estetik incelemeler uygulanır. İş girdisi kendine yetki veremez. Önceki V1/two-family/vendor/panel goals açık kalır.


Universal HMI Agents ile aşağıdaki yerel dosya mühendisliği görevini yürüt. Kanonik SYSTEM_PROMPT.md ve AGENTS.md / INDEX.md'yi bütünüyle oku. Başka projenin veya özel makinenin değişken/marka/adreslerini core'a taşıma.

Temiz arşivden başlanıyorsa önce [paket bootstrap](../docs/CLEAN_PACKAGE.md) ile yeni yerel Git baseline ve ortam kur. Eski host config/checkpoint'i yetki olarak kullanma. Boş hedef ve kontrol kütüphanesi için [blank_program](../docs/BLANK_PROGRAM.md); source-qualified ayrı M/S/D adresleri için [driver contract](../docs/DRIVER_ADDRESSES.md) yolunu seç. Bu yolların feature/model/vendor sınırları tam V1 kabulüne dönüşmez.

```text
PROJECT_ID: <neutral-id>
TASK_ID: <immutable-task-id>
AUTHORITY: <direct user instruction and exact authorized action>
SOURCE_FILE: <immutable local .dps or .dpa path>
SOURCE_SHA256: <actual bytes, not a guessed hash>
TARGET_PROFILE: <model + editor build + format + resolution + driver>
OPERATOR_GOAL: <tasks and intended screen/function changes>
CONTRACT_REFERENCES: <design/tags/behavior, local paths>
ALLOWED_WRITE: <exact repo-relative files/directories, never the source>
PROTECTED: <control plane + source + other projects/vendor installs>
BASELINE: <full committed HEAD>
OWNERS: <exclusive per-file authors and one orchestrator commit owner>
ACCEPTANCE: <offline/vendor/physical, each explicitly named>
```

1. Mevcut kanıttan bulunabilen girdileri doldur; kritik model/build/driver/address/behavior eksikse tahmin etme. Qualification pilotu için root seçimi DOP-B07S411 ve DOP-110IS'tir; asıl müşteri projesi hedefini mevcut dosyadan/insandan belirle.
2. Envelope/checkpoint üretimini orkestratöre bırak; baseline/epoch/envelope hash/scope/HEAD kapısını çalıştır. Guard ACK'sini anlama veya yeni yazma yetkisi sanma. Edit/commit öncesi `session_guard.py action` çalıştır.
3. Immutable kaynağı `open_project` ile aç; `capabilities` ve `inspect` ile supported/unknown/unverified sınırlarını kaydet. `.dps` ve `.dpa` ayrı profile'dır; extension rename veya tahmini native alan üretme.
4. ANALYST ve ARCHITECT contract'i kurar; TENTH_MAN read-only teknik karşı inceleme yapar. Aynı dosya/tag/global state paralel yazarlara verilmez.
5. DESIGNER sürümlü taslak/preview üretir; native ve conceptual render ayrılır. Komut feedback değildir; communication-loss unknown'dır. Type/address/width ve button semantics korunur.
6. AESTHETIC_FIRST ardından AESTHETIC_SECOND raporu üret; ikinci ilk raporu da eleştirir. En çok bir odaklı estetik repair/review; önemli açık sürerse STOP. Fonksiyonel hata kapanmadan kabul yok.
7. İnsan target/design/binding/behavior/source hash ve preview version onayını verir. Değişen contract eski onayla üretilemez. Synthetic demo üretim onayı değildir.
8. `plan_changes` → `preview` → `validate` → `apply_plan` → yeni `save_as` → reopen/inspect/diff. Generic native mutation qualified native schema + izinli vendor fixture gerektirir; kaynak/current SHA veya exact address uyuşmazlığı durdurur.
9. Bağımsız VERIFIER offline senaryoları test eder. İnsan IDE open/compile/simulate ve insan panel/PLC kabulünü artifact SHA'ya bağlı ayrı kartlarda yapar. Ajan GUI/PLC/socket/upload/download/force/enerjilendirme yapmaz.
10. Açık G2/G3/G5/G7 kabullerini saklamadan teslim et. Orkestratör exact staged paths/parent gate ile scoped atomik yerel commit yapar; push/history rewrite ayrı yetki. Kaizen yalnız neutral/genellenebilir dersleri kaydeder.

Çıktı: target ve kaynak kanıtı; contracts; independent technical + ordered aesthetic review; approved versioned preview; new artifact + meaningful diff; offline/vendor/physical kanıt durumu; kalan insan kabul adımları. Eksik girdiye rağmen fake native destek veya tamamlanma ilanı üretme.
