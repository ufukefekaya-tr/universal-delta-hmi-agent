# Açık INT16/F0 saklama dönüşümü

Bu ayrı yol **DOPSoft2 / DOP-B10S615 / raw4.00.07.04** için kaynakla doğrulanmış yeni numeric clone'u unsigned16'dan signed16'ya dönüştürür. Mevcut kaynak ve property görselleri UINT kalır; signed donor bulunmuş gibi sunulmaz. Dayanak vendorun primary native reader/writer/compiler/renderer static davranışıdır. DLL/IDE çalıştırılmaz; runtime için vendor kurulumuna veya bu PC'nin yoluna bağımlılık yoktur.

`native_schema.storage_conversion` qualified/version1/mode `source_uint16_to_int16_f0` içerir. Kaynak, iki full donor extent ve registered authority SHA'ları pinlidir; bounded review reference metni hashed schema içinde kaydedilir. Asıl altı kontrol library'si ve property kanıtları korunur. Model/family/serialized version, exact width/mappings ve bütün disabled flags/operands yeniden doğrulanır. [Statik authority](../profiles/numeric_contracts/dopsoft2_b10_int16_conversion.json).

Native `convert_numeric_storage` yalnız fresh clone'a explicit `data_type: INT` uygulanır: **MemLen1 değişmez; MemFmt2→1**. Eski `configure_numeric` storage eşitliği kuralını korur; ayrı dönüşüm sonrasında INT ayarı yapılır. Kaynak owner, button, arbitraryID, tekrar veya yanlış sıralı dönüşüm reddedilir. Final dosyada yalnız validated signed clone'un format değişimi normalize edilerek kaynak bütünlüğü kontrol edilir.

Input: canonical integral−32768≤minimum<maximum≤32767; F0; I1..5 ve iki endpoint için yeterli digit. Display'e MinValue/MaxValue alanı eklenmez. Gain1/Offset0/Roundoff0; dormantOffsetMemFmt ve None offset/lock/trigger/keypad/macro kaynak byte'ları exact kalır. INT fractional, gain/offset/roundoff dönüşümü, geniş/floating/TIME veya başka model/family bu sözleşmeyle açılmaz. UINT fixed-display descriptor'ı birlikte kalabilir; onun F0..4 kabulü INT'e aktarılmaz. D adresi aynı fiziksel16bit word syntax/Link/MemType ile kalır; INT catalog tipi ayrıca explicit olmalıdır.

```text
python scripts/calibrate_integer_storage.py --workspace projects/ornek --source inputs/controls.dps --library-profile contracts/source_controls_v1.json --output-dir contracts/int16/R001 --review-reference "Bağımsız statik dönüşüm incelemesi"
```

Helper yalnız yeni profile/calibration JSON üretir. Kaynağın üzerine yazmaz; previous authority/witness/profile/property ve yeni authority publish/save öncesi fresh kalır. Çıkan `source_controls_int16_static_v1` library [blank target](BLANK_PROGRAM.md) veya [multipage](MULTIPAGE_PROGRAM.md) helper'ına verilir; stdio sunucu proje-local registry ile başlatılır. Caller `qualified`/SHA değiştirerek registered proof'u genişletemez. Native makine adayı için sürüme bağlı tasarım/teknik/estetik ve insan onayı gerekir. Neutral adapter test yetkisi makine onayı değildir.

[623-test kanıtı](../reports/INT16_STORAGE_MILESTONE.json), [bağımsız denetim](../reports/INT16_STORAGE_REVIEW.md), [gerçek dosya](../reports/INT16_STORAGE_GENUINE_PROBE.json). Kabul **STATIC_SOURCE_QUALIFIED_STORED_CONFIGURATION_ONLY**; signed donor/property NOT_FOUND, nativepixel/derleme/keypad/runtime/PLC/panel NOT_RUN. Tam V1 ve DIAScreen kabulü açık. Temiz eski RAR bu sonraki kodu içermez.
