# Kanıt modeli

Her kanıt kartı exact **profile + feature + scenario + artifact SHA-256 + test revision** taşır. Profile kimliği model/editor build/format/resolution/driver ve profile dosyası hash'ini kapsar. Düz "test geçti" ifadesi destek kaydı değildir.

| Kaynak | Kanıtladığı | Kanıtlamadığı |
|---|---|---|
| Syntax/import/unit/integration | Test edilen offline davranış | Vendor open/compile veya gerçek panel |
| Neutral synthetic fixture | Parser/roundtrip/validation/preview senaryosu | Gerçek vendor format şeması ve model desteği |
| İzinli gerçek vendor fixture | Exact native schema/feature parse ve roundtrip araştırması | İnsan IDE kabulü ve fiziksel davranış |
| İnsan IDE open/compile/simulate | Exact editor build ve artifact için vendor senaryosu | Fiziksel PLC/panel feedback ve wiring |
| İnsan panel/PLC testi | Exact cihaz, artifact ve fiziksel senaryo | Başka model/aile/driver kombinasyonları |

Durumlar: `UNVERIFIED`, `OFFLINE_PASS`, `VENDOR_PASS`, `PHYSICAL_PASS`, `UNSUPPORTED`. Skip/boş test veya fixture olmayan test koleksiyonu PASS değildir. Native qualification bekleyen profile'ı sahte unsupported wrapper olarak tamamlamaya işaretleme.

## Kart zorunlulukları

- Exact profile ve contract; feature ve scenario. Type/address/button/comm-loss gibi özellikler ayrı kart olabilir.
- Artifact yolu veya yerel reference, SHA-256, immutable source SHA, output SHA ve test revision.
- Executor türü (`agent_offline` / `human_vendor` / `human_physical`), tarih, araç/editor build ve sonuç.
- Senaryo adımları, expected/actual, test sayısı, skipped sayısı, açık bulgu ve kanıt reference'ları.
- Native qualification için schema revision/hash, izinli vendor fixture SHA ve ilgili feature/scenario kapsamı.

Public core'a gerçek müşteri adı, makine PLC tag'ları, adres/IP, lisansı belirsiz vendor örneği veya özel ekran görüntüsü kopyalanmaz. Evidence card nötr metadata/relative ignored reference kullanabilir; test edilen dosya özel kalır. Fixture provenance/lisans açık değilse dağıtma.

İnceleme bulgusu `tetikleyici → kanıt → etki → minimum düzeltme → tekrar test` zinciridir. Reviewer bağımsız read-only çalışır; estetik ikinci reviewer birinci raporu da eleştirir. İnsan onayı ve fiziksel kabul başka bir ajanın kanaatinden üretilemez.

[VENDOR_EVIDENCE](../templates/VENDOR_EVIDENCE.json) ve [PHYSICAL_EVIDENCE](../templates/PHYSICAL_EVIDENCE.json) örnekleri `UNVERIFIED` başlangıçlıdır. Alan doldurmak veya hash yazmak test yapıldığını tek başına kanıtlamaz.

## Bounded Alarm kanıtının kapsamı

Yeni public Alarm subset'i özgün SYNTHETIC/0.0 `.dps` ve `.dpa` envelope fixture'larında mevcut active-high BOOL primary-message mutation ve source-preserved Type11 current/history/strip identity/geometri/clone sözleşmesini sınar. Mapping source-local'dır; message raw SHA, explicit one-bit storage, bütün altı native guard, exact tag/address/link ve all-enabled coverage kartta belirtilmelidir. Bir field hash'inin doğru olması width, owner veya watched formatting semantiğini qualified yapmaz.

View için full source owner SHA ve yalnız Element identity/geometri kayıtlarını dışarıda bırakan immutable Element+State digest ayrı kanıttır. Font, title, columns, date/time, movement, secondary language, unknown presentation ve State raw bytes'ının korunması, bunların vendor semantiğinin veya candidate pixel görünümünün kabulü değildir. Foreign owner, active reference veya executable macro pinli SHA ile yetkilendirilemez. Alarm history_policy/view_policy preserve_source kaynak davranışını değiştirmeme sözleşmesidir; retain/clear, persistence, lifecycle, acknowledgment veya tarih/saatli storage implementation kanıtı değildir.

Pure expected tail karşılaştırması approved primary-message batch dışında disabled/secondary message, trigger/address/global scalar ve unrelated prefix/suffix/process-history drift'ini sınamalıdır. Contract mevcutken boş alarm listesi all-enabled kontrolünden geçmelidir; yalnız contract yok ve alarm IR boşsa opaque byte preservation geçerlidir. No-op test değişiklik testiyle aynı provenance/type/coverage kapılarından geçer ve bütün source bytes'ını korumalıdır.

Adversarial kaynak yeniden hash'lenerek qualified metadata'ya taşınsa bile grammar ve trigger-shape gate'i korunmalıdır: kısa/uzun message/alarm/watch index spellings ve primary scalar companion'a eklenen subindex unqualified kalır. Kinds/donors null/list gibi malformed map'ler automatic/explicit/pure verifier yollarında typed HmiError vermelidir; raw runtime exception güvenilir reject kanıtı değildir. [A5–A7](../kaizen/ALARM_VIEWS.md) test/repro sınırını kaydeder; hash eşitliği bu grammar/owner/shape kabulünün yerine geçmez.

Conceptual preview'deki SOURCE-PRESERVED PRESENTATION/UNKNOWN ve NO HISTORY DATA placeholder'ları desteklenmeyen native görünümü açık gösterir. Örnek değerin aktif/pasif olması bu placeholder'ı native veya sağlıklı kabulüne çeviremez. Önceki 297-test unit kanıtı (tarihsel yerel kanıt; genel pakete dahil değil: `../reports/history/297/README.md`) yeni Alarm revision'ını kanıtlamaz; exact yeni suite, bağımsız adversarial review, fresh checkout ve manifest/scoped commit kapanışı [güncel raporda](../reports/VERIFICATION.md) ayrı kaydedilir. Bu belge yeni PASS sayısı veya revision uydurmaz. Selected-model fixture, vendor/simülasyon/panel ve Linux/macOS kabulü açık kalır.
