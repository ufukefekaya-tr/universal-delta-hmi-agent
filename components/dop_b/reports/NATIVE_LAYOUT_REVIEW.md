# Bounded layout — bağımsız teknik denetim

**Sonuç: OFFLINE_PASS.** Uygulayıcıdan ayrı `/root/emitter_counterreview` salt okunur çalıştı. Kabul yalnız revision `0b2eeee4f6ee03fab00b287c5cf17dc0e291555b1b61a5bb8e696fab43c95b8d` için bounded sentetik native dosya sözleşmesidir; tam V1/native görsel/vendor/panel kabulü değildir. [Hash ve test kaydı](NATIVE_LAYOUT_MILESTONE.json).

Bağımsız koşu: **263 benzersiz test**, 0 failure/error/skip, 29.98 saniye. 40 kaynak hash’i koşu boyunca değişmedi. İlk 244-test ve sonraki 257/259-test root sonuçları ilgili açıkları kaçırmıştı; yalnız son revision için bu kabul verildi. Test sayısı tek başına teslim kapısı sayılmadı.

## Karşı örneklerin kapanışı

| Bulgu | Tetikleyici → kanıt → etki | Düzeltme → bağımsız tekrar test |
|---|---|---|
| S1 — önemli | Boş donor’da BaseScreenID/ScreenLockVar; önceki kontrol kabul etti, yeni sayfa gizli arka plan/kilit taşıdı | Tam yedi Screen kaydı, empty Aux/owned extents, immutable empty donor ve saved page signature; automatic/explicit final reddi PASS |
| S2 — önemli | State-only fill guard’ı atladı; NumBgOpacity/BtnPictureStretch gibi kind prefix’leri ve extra mapping exemption kaçtı | Bütün controlled nesnelerde typed companion kontrolü, observed alan taraması ve mapping whitelist; bare numeric/text, 0/1-only gösterge, unit/picture/opacity karşı örnekleri PASS |
| S3 — önemli | Order=0, append-only/no-op yolunda kabul edildi; stream dışında unqualified sıra vardı | Original ve candidate üzerinde complete layout guard; Screen/Element/State, auto/explicit/saved check PASS |
| S4 — küçük | Unowned opaque State macro owner=None, page scan’de raw exception verdi | Typed owner kontrolü; opaque program byte’ları korunarak yeni boş page üretimi PASS |
| S5 — küçük | Malformed state_fill=None/list/bool/list-field, final comparison’da raw exception verdi | Shared typed style guard önce çalışır; explicit no-op typed NATIVE_STYLE_UNVERIFIED PASS |
| S6 — önemli | Explicit extra ConFirmWindow/CloseScreen/Variation yazımı IR değişmeden kabul edildi | Public operation-intent yalnız fixed IR field/scope/declaration; extra, remapped x, undeclared color ve nonprimary caption edit kapalı; low-level primitive ayrı PASS |
| S7 — önemli | Type-only goto kind ve SubType99, explicit no-op final’da navigation sayıldı | Complete canonical Type/SubType/target sözleşmesi automatic ve final’da; partial kind reddi PASS |

İki envelope ailesinde **52** bağımsız bellek karşı örneği beklenen sonuç verdi, raw exception veya kaynak yazımı olmadı. Denetmen ayrıca iki opaque corruption denedi: Application içindeki kontrol edilmeyen veri ve envelope prefix değişimi. `save_as` checked candidate receipt SHA’sı nedeniyle `SAVE_INTEGRITY` verdi; destination ve temporary residue oluşmadı, kaynak byte eşit kaldı.

Native helper’lar ayrıca 78-test focused koşuda denetlendi. Plain-page helper yeni sayfa için dar bir baseline’dır; mevcut her sayfanın native alanlarını yedi kayda indirgemez. Order guard yalnız competing kayıtları reddeder, vendor pixel/z-order qualification vermez. ASCII dışında navigation companion üretimi kapalıdır; ID-only kayıtta var olmayan companion oluşturulmaz.

## Kaynak ve kabul sınırları

Source-local font ve paired-goto gerçek FullDemo holdout’ları iki dar değişiklikle yeniden okundu; diğer kayıtlar korundu. Kaynak modeli seçilmiş DOP-110IS değildir; candidate’lar bellekte kaldı. [Araştırma kanıtı](NATIVE_LAYOUT_RESEARCH.md). Native scalar metni/COLORREF değerinin doğruluğu, gerçek katman/şeffaflık/font/piksel görünümü PASS anlamına gelmez.

Public save_as hâlâ SYNTHETIC/0.0 ile sınırlıdır. Text77/indicator78 tamamen özgün test enumlarıdır. Units, native vendor görünüm/layer, external driver, public Alarm strip/table/history ve exact selected-profile üretim açık kalır. Önceki makro/global kaynak kabulü kendi revision’ında tarihsel raporlara (tarihsel yerel kanıt; genel pakete dahil değil: `history/225/README.md`) bağlıdır. `build_profiles.py` tarihsel development generator’ıdır; setup tarafından çalıştırılmaz, güncel calibrated registry’yi yeniden üretme aracı olarak sunulmaz.

Committed kaynak `215e4267a7f3694e7a71822e005ca4e20f3e9125`, ayrı Windows clone/yeni venv içinde aynı 40 kaynak hash’i/revision ile 263/263 sıfır failure/error/skip geçti. [Taşıma doğrulaması](relocation_verification.json), [testler](relocation_tests.json). Ortamın bağımsız denetimi **OFFLINE_PASS**: actual source HEAD/40 hash ve 263 ID aynı, 30 pin/pip check, editable direct_url/import ve eski PATH/sys.path izolasyonu, gerçek .git dizini ile origin/alternates yokluğu doğrulandı; aynı fiziksel Windows host’unda farklı konum/ortam kanıtıdır, ikinci PC/Linux/macOS kabulü değildir.
