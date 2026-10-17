# Literal sayfa üretimi — donor ve kanıt sınırları

Bu kayıt yalnız tarafsız literal_page_generation dersidir; private source/vendor asset içermez. Exact final test/revision ve genuine kaynakta varsa memory-only gözlem [root raporunda](../reports/VERIFICATION.md) ayrıca dondurulur. Yeni run/PASS veya vendor-valid hükmü değildir. [Kılavuz](../docs/LITERAL_PAGE_GENERATION.md) dar kullanım yolunu anlatır.

## L1 — Donor pin'i feature calibration değildir

- **Tetikleyici:** Donor SHA doğruyken active lock/action/macro/address, sound/picture veya unknown/duplicate/secondary field yeni bloklara miras kalır.
- **Kanıt:** [LiteralGenerationTests.test_source_donor_behavior_address_and_unknown_variants_rejected_after_repin](../tests/test_native.py), test_missing_repeated_unkeyed_and_secondary_caption_donor_fields_fail ve test_literal_contract_exact_shapes_fingerprints_donors_and_mode; native `_literal_donors()`.
- **Kök neden / karşı görüş:** Hash byte kimliğidir. “Doğru pin donor'ı inert yapar” görüşü active/unknown alanın anlamını ve davranış qualification'ını karıştırır.
- **Etki:** Sabit text veya yeni header-only page intent dışındaki activity/dependency'yi taşıyabilir.
- **Minimum değişiklik:** Distinct mode/source/prefix/header/Aux/full owner pin'ine bounded required/allowed raw shape ve explicit inert companion gate ekle. New page yalnız Screen+empty Aux; source numeric/function owner'ları miras olmaz. Managed ID/name/geometri/caption dışındaki yeni header/State byte'ları donor ile aynı kalır.
- **Regresyon:** Native named testler ile [test_new_header_only_empty_page_does_not_inherit_any_function_owner](../tests/test_service.py) ve test_header_only_page_copies_no_bound_numeric_function_or_state_objects. Exact root run sonucu ayrıca gerekir.
- **Rollback:** Uygunsuz donor ile output yoktur; source'u normalize ederek gate'i aşma. Yetkili uygun kaynak/donor ve yeni mode-bound plan/onay kullan; original source korunur.
- **Sınır:** Bu literal framing/raw baseline'dır; font/sound/picture/flag enum, layer/driver/macro/vendor/panel feature qualification'ı değildir. Graph UNKNOWN kalır.

## L2 — Donor immutable source'dan çözülür

- **Tetikleyici:** Önce appended page/owner üretilir, sonra yeni nesne veya mutable source projection'ı clone donor yapılır.
- **Kanıt:** Native `_literal_operation()` immutable original extent'i kullanır. [test_source_pin_is_immutable_and_candidate_needs_actual_original](../tests/test_native.py), [test_explicit_missing_extra_and_wrong_operations_cannot_cover_generation_intent](../tests/test_service.py).
- **Kök neden / karşı görüş:** “Transaction'da oluşan nesne artık uygun donor” görüşü frozen sözleşmeyi değişen graph'a bağlar ve önceki hatayı çoğaltır.
- **Etki:** Audit'te bulunmayan inherited style/state/address intent dışı yayılabilir; pin gerçek clone kaynağına ait olmayabilir.
- **Minimum değişiklik:** Header+Aux ve full text owner immutable kaynaktan çözülür. Page ID positive canonical/fresh; new element ID project-wide fresh. Original pages/native_preserved owner sıra/hash/geometri byte-exact kalır. Explicit operations approved IR'ın exact generated operations'ından ayrılamaz.
- **Regresyon:** Named testlere ek test_new_project_wide_id_collisions_zero_and_noncanonical_ids_are_rejected, test_original_owner_caption_and_original_page_name_edits_are_rejected, test_saved_candidate_extra_block_or_retained_region_changes_cannot_be_delivered [service regresyonları](../tests/test_service.py).
- **Rollback:** Candidate donor yapılamaz; original source'tan yeni session/contract/plan ve gerekli insan onayı oluşturulur. Failed output yalnız işlem sahipliği doğrulanarak kaldırılır; source overwrite yoktur.
- **Sınır:** Immutable donor yeni button/numeric/alarm veya generic graph clone yetkisi değildir. Existing-owner edit ve literal append ayrı modlardır.

## L3 — Dosya adayı graph/execution kabulü değildir

- **Tetikleyici:** Appended blocks doğru UTF-16/ID/geometri/gzip ile reopen olur; original opaque globals/prefix/tail aynı kalır. Unknown metadata yine page/owner sayısına bağlı olabilir.
- **Kanıt:** Service `_generation_document()` pure expected payload'ı setter'dan ayrı türetir. [test_both_envelopes_generate_real_saved_pages_without_source_object_inheritance](../tests/test_service.py), test_generation_preview_is_text_intent_and_not_native_pixel_or_execution_proof; [test_appended_literal_page_generation_full_transaction_over_sdk_stdio](../tests/test_stdio.py).
- **Kök neden / karşı görüş:** “Source byte'ları korundu, parse geçti; vendor çalışır” görüşü opaque graph semantiğinin çözüldüğünü varsayar. Thumbnail retention yeni ekran render'ı değildir.
- **Etki:** Deneysel aday gerekli native/vendor/panel kabulü olmadan executable veya panel-ready sanılabilir.
- **Minimum değişiklik:** New block variable ID/geometri/primary UTF-16 extent'i ve gzip generation ayrı dosya özelliğidir. Receipt OFFLINE_NATIVE_CANDIDATE, opaque_graph_dependencies UNKNOWN, program_writer_complete false, native visual/vendor/physical NOT_RUN bildirir. Preview yalnız text/coordinate intent'tir; BMP/prefix/tail/original blocks korunur.
- **Regresyon:** Named byte/preview/stdio testleri ve [test_generation_requires_exact_human_approval_for_non_synthetic_identity](../tests/test_service.py). Fixture içindeki fabricated human_reference gerçek reusable insan onayı değildir.
- **Rollback:** Vendor-valid hükmü veya panel download yoktur. Kullanıcı vendor open/save/compile/görünümü kontrol eder; yeni save SHA'sı yeniden inspect/diff/kanıta bağlanır. Bulguda kabul açık ve original source geri dönüş girdisidir.
- **Sınır:** Genuine public B07E515 memory-only gözlemi varsa exact source/model/revision kanıtıdır; asset reusable repo'ya taşınmaz. Selected B07S411/DOP-110IS, family-wide, command/driver/new alarm, full writer veya G4/G5/G7 kabulünü kapatmaz.
