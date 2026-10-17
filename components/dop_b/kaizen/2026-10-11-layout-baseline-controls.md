# Layout baseline ve guard dersleri — 2026-10-11

Kaynak: bounded layout incelemesi, [native](../tests/test_native.py) ve [service](../tests/test_service.py) regresyonları. İlk S1–S4 kayıt revision'ı `67c902257a505f58b8e75d7b4d80bd0c9a27a729da54979bdb6b5a4227fe0d08` tarihseldir; S5–S7 ile kaynak tekrar değişmiştir. Güncel exact source hash/test listesi [root test raporundan](../reports/python_tests.json) okunur. Bu ders test çalıştırma veya teslim kabulü değildir: bağımsız reviewer S1–S7 tekrar testi [layout milestone](../reports/NATIVE_LAYOUT_MILESTONE.json)/[review](../reports/NATIVE_LAYOUT_REVIEW.md) ile **bounded OFFLINE_PASS** kaydeder; Windows fresh clone [OFFLINE_PASS](../reports/relocation_verification.json); **bağımsız ortam denetimi PASS; manifest hash eşitliği ve scoped proof commit kapanışı Git/checkpoint üzerinden doğrulanır**. Özel proje, vendor payload veya kişisel host yolu içermez.

## S1 — Önemli: boş nesne listesi inert sayfa kanıtı değildir

- **Tetikleyici / kök neden:** Empty-page donor, yalnız `elements=[]` ile güvenli sayıldı; page-level background, BaseScreenID veya lock inheritance görünmedi.
- **Kanıt:** `test_new_page_background_and_lock_rejected_for_automatic_and_explicit_plans`, `test_saved_new_page_cannot_gain_undeclared_page_baseline` ve native plain-page baseline regresyonları.
- **Etki:** Yeni sayfa tasarımda bildirilmeyen background/lock/davranışı devralabilir; boş preview bu native contract'i temsil etmez.
- **Karşı görüş / minimum fix:** Gerçek projede inheritance meşru olabilir; unknown alanı silmek çözüm değildir. Yeni donor için yalnız VER=16, ID, framed wTextLen, DocSizeX/Y, PanelSizeX/Y tam yedi alanı, immediate empty Aux ve known extents kabul et. Nesnesiz/inert donor ile saved yeni page baseline SHA'sını karşılaştır; ID/name ve defined object bytes signature dışındadır, object extent kontrolü devam eder.
- **Negative regression:** Automatic ve explicit clone'a background/lock/extra kayıt ekle; saved candidate'a sonradan BaseScreenID ekle. `UNQUALIFIED_PAGE_BASELINE`, unapplied sonuç ve immutable source beklenir.
- **Rollback:** Candidate'ı bırak, yeni-page mutation yolunu kapalı tut; kaynak lock/background alanını silerek testi geçirme.
- **Genellenebilirlik sınırı:** Yedi-field baseline yalnız dar plain-page sözleşmesidir; mevcut bütün sayfalar bu şekle indirgenmez. Vendor page schema, model veya inheritance desteği kabulü değildir.

## S2 — Önemli: görünüm kontrolü çağrı yolu ve field adıyla kaçabilir

- **Tetikleyici / kök neden:** State-only fill, top-level style yokken companion guard'ını atladı. Yalnız leading-prefix taraması NumBgOpacity, BtnPictureStretch/CtrPicture*, FieldFontSize/ScaleFont* ve Range/TargetOpacity alanlarını kaçırdı.
- **Kanıt:** `test_state_only_indicator_fill_checks_appearance_even_for_exact_noop`, `test_kind_prefixed_numeric_appearance_cannot_bypass_companion_contract`, `test_visual_schema_cannot_exempt_unqualified_appearance_through_extra_mapping`.
- **Etki:** Bildirilen düz fill/font/color scalar doğru olsa bile opaque picture/gradient/opacity farklı native görünüm üretebilir; extra visual key field'ı yanlış editable saydırabilir.
- **Karşı görüş / minimum fix:** Exact companion baseline ile bilinen raw alan korunabilir; isimden vendor semantiği çıkarılmaz. State-only fill'e aynı guard'ı uygula; Font/Picture/PIB/opacity/shadow/gradient substrings ve diğer appearance alanlarını owner bazında kapsa. Yalnız whitelist mapping editable olsun; unknown key exemption vermesin. PictureOffset/PIB Name/Picture Name flat-style yolunu kapatsın.
- **Negative regression:** State-only/no-op ve numeric automatic/explicit planlara gradient, PIB, kind-prefix opacity/font/picture alanı veya extra mapping ekle. `NATIVE_STYLE_UNVERIFIED`, unapplied sonuç ve source preservation beklenir.
- **Rollback:** Appearance mutation'ı durdur, candidate'ı bırak; bilinmeyen görsel alanı silme veya empty companion baseline'a zorla uydurma.
- **Genellenebilirlik sınırı:** Empty-companion registry contract'i yalnız özgün synthetic fixture içindir. Substring guard vendor renderer değildir; font scalar points/pixels eşitliği, flat-style veya native pixel kabulü üretmez.

## S3 — Önemli: no-op ve append-only, layer denetiminin istisnası değildir

- **Tetikleyici / kök neden:** `Order` kontrolü reorder operation'ına bağlı kaldı; sıra değişmeyen veya yalnız sona nesne ekleyen plan bu kapıdan geçmedi.
- **Kanıt:** `test_competing_order_rejected_without_reorder_in_append_and_explicit_noop`, `test_layout_guard_rejects_order_even_for_zero_append_only_and_noop_pages`.
- **Etki:** Section sırası korunurken native `Order` farklı/kalibre edilmemiş layer temsilini taşıyabilir; `Order=0` zararsız default diye yorumlanamaz.
- **Karşı görüş / minimum fix:** Section sırası bazı bounded fixture'larda anlamlıdır; bu native Order semantiğini kanıtlamaz. Public preflight ve final candidate'da pure `verify_layout_order()` çalıştır; bütün Screen/Element/State Order alanlarını, 0/no-op/append-only dahil, reddet. Complete extents, immediate empty Aux ve Application-only prefix kontrolünü koru.
- **Negative regression:** Her üç owner'a `Order=0` ekle; automatic append ve explicit empty operations ile dene. `UNQUALIFIED_LAYER` ve değişmeyen kaynak beklenir.
- **Rollback:** Order/layer mutation yolunu kapalı tut, candidate'ı bırak; kaynak Order alanını kaldırarak belirsizliği gizleme.
- **Genellenebilirlik sınırı:** Bounded section permutation gerçek z-order veya vendor layer qualification değildir; kalibre edilmemiş competing representation ayrı contract gerektirir.

## S4 — Minor: owner yokluğu okunabilir durum olmalıdır

- **Tetikleyici / kök neden:** Opaque macro inventory kaydındaki `owner=None` üzerinde `.get()` çağrısı empty-page preflight'ı çökertti.
- **Kanıt:** `test_unowned_opaque_macro_does_not_crash_empty_page_preflight` unknown macro bytes'ını mevcut nesnede tutarak yeni inert page preflight'ını sınar.
- **Etki:** Parse edilmiş fakat sahibi belirlenememiş retained veri, unrelated bounded işi beklenmeyen exception ile keser.
- **Karşı görüş / minimum fix:** Unknown owner mutation için qualified değildir; korunabilir opaque kaydı uydurma owner'a bağlamak da yanlıştır. Page ownership okumadan önce dict türünü denetle; unowned bytes'ı retained bırak, owner/komut semantiği icat etme.
- **Negative regression:** Inventory'de owner=None doğuran opaque macro ekle. Preflight crash olmamalı; candidate exact opaque payload'ı ve source bytes'ını korumalıdır.
- **Rollback:** Candidate mutation'ı kapatıp inspect/preservation'a dön; macro'yu silme, normalize etme veya rastgele page owner ata.
- **Genellenebilirlik sınırı:** Null-tolerant inspection unknown macro execution, clone veya semantic mutation yetkisi vermez. Bu minor robustness düzeltmesi S1–S3 fonksiyonel kabulünün yerine geçmez.

## S5 — Minor: malformed mapping typed hata olmalıdır

- **Tetikleyici / kök neden:** State-fill mapping None/list/boolean veya field=list iken shape doğrulanmadan `.get()`/field lookup çalıştı; explicit no-op da bu yolu kullandı.
- **Kanıt:** `test_explicit_noop_malformed_state_fill_returns_typed_error` invalid mapping biçimlerini current source'a uygular.
- **Etki:** Qualification hatası kontrollü HmiError yerine runtime exception olur; no-op hata biçimi farklılaşır.
- **Karşı görüş / minimum fix:** No-op mapping ihtiyacını ortadan kaldırmaz. Dict, exact field/scope/type/range/encoding önkoşullarını kullanmadan doğrula; malformed metadata'yı normalize ederek qualified sayma.
- **Negative regression:** None, list, True ve field=list ile explicit empty plan dene; `NATIVE_STYLE_UNVERIFIED`, unapplied sonuç ve unchanged source beklenir.
- **Rollback:** Mutation'ı kapalı tut, kaynak inspect edilebilir kalsın; invalid profile'ı sessiz default mapping ile onarma.
- **Genellenebilirlik sınırı:** Typed hata format/feature qualification değildir; null-tolerant inspection ile mutation precondition'ı ayrıdır.

## S6 — Önemli: qualified primitive public IR yetkisine dönüşmez

- **Tetikleyici / kök neden:** Extra set_property, ConFirmWindow/CloseScreen/Variation gibi IR'da olmayan davranışı değiştirdi; final verifier yalnız represented intent'i karşılaştırdı.
- **Kanıt:** `test_explicit_extra_native_behavior_property_is_not_an_ir_transaction`, `test_known_property_cannot_write_an_unrepresented_style_or_remapped_field`.
- **Etki:** Approval/preview aynı görünürken public plan ek davranış veya remapped field yazabilir; low-level property calibration fazla public yetki üretir.
- **Karşı görüş / minimum fix:** Qualified low-level primitive ayrı iş için kullanılabilir. Public operation intent yalnız fixed IR key↔field↔owner, button behavior ve açık scalar/state intent kabul etsin; non-primary set_text mutation kapalı kalsın. Ara geometry değerleri meşru olabilir; actual equality final verifier'da kalır. save_as semantic doğrulamadan sonra apply receipt candidate SHA'sını da denetlesin.
- **Negative regression:** Extra davranış, x→CloseScreen veya IR'da olmayan color yazımı `NATIVE_OPERATION_INTENT` ile durmalı. `test_save_receipt_detects_opaque_candidate_corruption_without_creating_output` semantic görünümü değiştirmeyen opaque byte corruption'ında `SAVE_INTEGRITY` ve output yokluğu bekler.
- **Rollback:** Public mutation gate'ini kapat, candidate'ı bırak; IR'ı karşılamayan alanı silme veya geçmiş approval'ı genişletme.
- **Genellenebilirlik sınırı:** Raw primitive capability public feature/approval değildir. Retained diğer dil kayıtları korunabilir; multilingual mutation/native visual/vendor kabulü oluşmaz.

## S7 — Önemli: partial kind yanlış navigation davranışını gizler

- **Tetikleyici / kök neden:** Goto kind yalnız Type içerince yanlış SubType=99, explicit no-op'ta aynı partial mapping'e uydu.
- **Kanıt:** `test_partial_navigation_kind_cannot_pass_automatic_or_explicit_noop`, `test_explicit_noop_navigation_requires_ascii_companion_encoding`.
- **Etki:** Target ID/name doğru görünse bile nesnenin gerçek behavior kind'i onaylı navigation değildir; name encoding eksikliği de no-op'ta gizlenebilir.
- **Karşı görüş / minimum fix:** ID-only native goto source olabilir; name record icat edilmez. Public preflight/final/no-op canonical exact Type+SubType seti ve navigation.match eşitliğini istesin; varsa actual target-name companion ASCII contract'e bağlı kalsın.
- **Negative regression:** Wrong SubType + Type-only mapping automatic/explicit no-op'ta `UNQUALIFIED_NAVIGATION`; mevcut name companion'da unqualified encoding final `NATIVE_DESIGN_MISMATCH` üretmeli, source değişmemeli.
- **Rollback:** Navigation mutation'ını kapat, candidate'ı bırak; unknown subtype/encoding'i yeniden adlandırıp onaylı sayma.
- **Genellenebilirlik sınırı:** Exact calibrated kind yalnız kendi profile/scenario'sunu kapsar; blanket model/driver/navigation veya native runtime kabulü değildir.

SYNTHETIC/0.0 public gate, new-only save_as ve gerçek selected-model/vendor/panel açıkları korunur. Kaynak değişirse eski test/run veya tarihsel Windows taşıma kanıtı yeni revision'a taşınmaz; final proof root tarafından ayrıca bağlanır.
