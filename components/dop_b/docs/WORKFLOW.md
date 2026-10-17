# Çalışma akışı

**0.2.0 headless yolu:** [Tek görev başlangıç yetkisi, workflow/goals ve teslim sınırı](HEADLESS_RELEASE.md). Etkileşimli insan onayı kuralları legacy akışta korunur; headless işte güvenilen başlatıcı policy’si ve exact bağımsız teknik/sıralı estetik incelemeler uygulanır. İş girdisi kendine yetki veremez. Önceki V1/two-family/vendor/panel goals açık kalır.


Kanonik kural [SYSTEM_PROMPT.md](../SYSTEM_PROMPT.md); bu belge uygulama sırasıdır. Offline araç kabulü, vendor kabulü ve fiziksel kabul ayrı kapılardır.

| Kapı | Girdi / eylem | Çıkış ve durma koşulu |
|---|---|---|
| W0 — Başlangıç | Üç control-plane dosyasının tamamını, rol kartını, envelope ve checkpoint'i oku; bootstrap/resume gate çalıştır. | Immutable baseline, raw-byte policy epoch, exact scope ve tek dosya sahibi. Uyuşmazlıkta edit yok. ACK okuma/anlama kanıtı değildir. |
| W1 — Hedef | Model, editor build, format, çözünürlük ve driver'ı kaynağa bağla. | TARGET_PROFILE. Pilot modeller DOP-B07S411 ve DOP-110IS; gerçek müşteri hedefi ayrıca doğrulanır. |
| W2 — Analiz | Kaynak SHA, ekran/nesne/tag kataloğu, komut ve feedback ayrımı; davranışlar ve veri tipleri. | Belirsizlik ve kapsam dışı listesi. `.dps` ile `.dpa` birbirinin alias'ı değildir. |
| W3 — Mimari / teknik karşı inceleme | Fonksiyon blokları, adres eşitliği, retained/unknown alanlar, güvenli çıkış ve kanıt sınırını read-only denetle. | TENTH_MAN bulguları; kritik açık kapanmadan üretim yok. Denetmen uygulama dosyasını değiştirmez. |
| W4 — Tasarım | DESIGN_BRIEF, sürümlü görsel taslak, bindings ve davranış sözleşmesi. | Kavramsal render açık etiketlenir; native preview yoksa varmış gibi sunulmaz. |
| W5 — Sıralı estetik inceleme | AESTHETIC_FIRST → rapor → AESTHETIC_SECOND. İkinci uzman ilk uzmanı ve uygulayıcıyı da eleştirir. | En çok bir odaklı estetik düzeltme ve tekrar inceleme. Önemli açık sürerse STOP. Fonksiyonel hata bu sınırdan muaf olarak kapanana kadar kabul açık kalır. |
| W6 — İnsan tasarım onayı | İnsan sürümlü preview'ı inceler; hedef/design/binding/behavior/source hash'lerini onaylar. | HUMAN_APPROVAL. Hash değişikliği onayı geçersiz kılar. Onay agent consensus'undan türetilemez. |
| W7 — Plan / uygulama | `plan_changes`, `preview`, `validate`; qualified native schema ve vendor fixture kapıları; `apply_plan`. | Tek immutable kaynağın güncel SHA'sı; exact address eşitliği. Generic qualified native schema yoksa native mutasyon durur. |
| W8 — Offline kayıt / doğrulama | `save_as` ile yeni dosya; kaydedilmiş dosyayı yeniden aç, `inspect`, `diff`, `validate`; bağımsız VERIFIER. | Kaynak değişmez, mevcut hedef üzerine yazılmaz. Unknown alan ve değişmeyen alan kanıtı. Boş/skip test PASS sayılmaz. |
| W9 — İnsan vendor / fiziksel kabul | İnsan IDE ile açar, derler/simüle eder; ayrı insan panel/PLC testi yapar. | Artifact SHA'ya bağlı VENDOR_EVIDENCE ve PHYSICAL_EVIDENCE. Ajan IDE/PLC/force/download yapmaz. |
| W10 — Kapanış | Açık kabul ve kanıt durumunu raporla; exact staged paths ve parent gate; scoped atomik yerel commit. | Push/remote/history rewrite ayrı yetki. Eksik kabul tamamlanmış ürün değildir. Orkestratör checkpoint günceller; tarafsız Kaizen kaydı bırakır. |

## Oturum ve scope kapısı

```powershell
python tools/check_repo.py --verify-bootstrap --policy-epoch
python tools/session_guard.py resume --task-id PROJECT-ID
python tools/session_guard.py action --task-id PROJECT-ID --kind edit --owner designer --paths projects/PROJECT-ID/design/brief.json
python tools/session_guard.py action --task-id PROJECT-ID --kind commit --owner root --paths docs/NEW_PROJECT.md
python tools/session_guard.py snapshot --task-id PROJECT-ID
```

`--root` her CLI için açık repo kökü olabilir. Envelope'deki owner adı kullanılır; örnek `designer` otomatik tanımlı bir hesap değildir. Edit gate dosya sahibini, allowed/protected logical ve resolved yollarını doğrular. Commit gate commit sahibini, mevcut HEAD'i ve tüm staged yolların tam eşitliğini doğrular; staging veya commit yapmaz. Guard, scope üstüne dosya sistemi mutasyonunu teknik olarak kilitleyen bir sandbox değildir.

Snapshot sadece stdout'a JSON verir, hiçbir dosyayı değiştirmez. Kapsam/hash/epoch halen geçerliyse ilerlemiş descendant HEAD'i kaydeder ve sequence'i artırır. Yalnız orkestratör checkpoint'i atomik olarak yazar. Compaction, handoff, yeni ajan veya uyuşmazlık sonrası W0 tekrarlanır. Scope/epoch değişimini sessizce eski envelope'a yamamak yasaktır; yeni yetki ve okunmuş politika kaydedilir.

Scoping root integration commit'e farklı yazarların dosyalarını birleştirme izni verir; kaynak dosya sahipliğini değiştirmez. Aynı dosya, global state, tag kataloğu veya fiziksel çıkış paralel yazarlara atanmaz. Kaynak/vendor kurulumları ve başka repolar scope dışıdır.
