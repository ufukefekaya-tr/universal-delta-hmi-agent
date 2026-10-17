# Native aday sınırları — C1–C6

Bu kayıt source-pinned mevcut text/geometri adayı ve native-preserved bütünlük kontrollerinden çıkan tarafsız dersleri taşır. Özel vendor/müşteri dosyası, owner kimliği, adres veya görsel içermez. Full HMI program writer, model/driver, native görünüm, vendor veya panel kabulü ilan etmez.

C1–C5'in **C6 öncesi tarihsel geliştirme referansı**: revision `72673a5889376d607d0f7103f1e7a6180448308c17934d1ef57f384d983f12c9`, 41 kaynak hash'i, root offline 400/400 test ve 0 failure/error/skip. Bu sayı yeni C6 kaynağının sonucu değildir. C6 sonrası kaynak revision'ı `9f62a01e77885a80a5aace8123788836a7bb0fbab73447f5043c78fbc6138236`'dır; güncel exact root run/hash sonucu [offline rapordan](../reports/python_tests.json) ayrıca okunur. Named regresyonlar bu belgede yeniden koşturulmuş ayrı kabul değildir; yeni host/vendor/panel kanıtı oluşturmaz. [Aday sözleşmesi](../docs/NATIVE_CANDIDATES.md) ve [mimari](../docs/ARCHITECTURE.md) kullanım sınırını tanımlar.

## C1 — Dosya oluşturulduktan sonraki guard hatası

- **Tetikleyici:** Atomic create-if-absent link işlemi tamamlanır; final freshness/approval kontrolünden hemen önce approval list/null/bozuk JSON olur veya approval/source/profile kaybolur.
- **Kanıt:** [ExistingOwnerCandidateTests.test_failed_post_link_input_guards_remove_only_the_created_candidate](../tests/test_service.py) iki envelope'da bu post-link koşullarını kurar. `save_as` final guard ve rollback akışı [service.py](../src/universal_hmi/service.py) içindedir.
- **Kök neden ve karşı görüş:** Ön doğrulama başarılı olsa da dosyalar final yayınlama anına kadar sabit kalmak zorunda değildir. “Temp dosya doğrulandı, kayıt tamamdır” görüşü son onay/kaynak bağının kopmasını gözden kaçırır; raw exception yolu oluşturulmuş adayı bırakabilir.
- **Etki:** Çağrı hata verirken yetkisiz/stale aday görünür hedefte kalabilir; kullanıcı failed dosyayı geçerli çıktı sanabilir.
- **Minimum düzeltme:** Metadata okumayı typed `HmiError` ile kapat. Link sonrası source/profile/calibration ve approval kontrolünü tekrar yap. Her final guard başarısızlığında yalnız bu çağrının oluşturduğu, receipt SHA'sına hâlâ eşit dosyayı kaldır; geçici dosyayı temizle.
- **Regresyon:** Named test created output ve `.uhmi-*` temp kalmadığını, dışarıdan silinmemiş kaynak byte'larının aynı kaldığını sınar. Önceden var olan hedefe yazma yetkisi eklenmez.
- **Rollback:** Başarısız candidate revision'ı teslim edilmez. Dışarıdan değiştirilmiş veya başka yazara ait dosya silinmez; immutable kaynak geri yazılmaz. Kaynak/onay geri gelir veya yeni sözleşme hazırlanırsa yeni revision ile yeniden başlatılır.
- **Genellenebilirlik sınırı:** Bu bir create-if-absent dosya transaction sınırıdır; panel download, vendor save, dağıtık kilit veya fiziksel güvenlik protokolü değildir. Haricî dosya silinmesini geri almayı garanti etmez.

## C2 — Mutable projection gerçek byte'lardan kopuyor

- **Tetikleyici:** Adapter'ın Document/Record projection'ı, envelope veya cache model/version/application alanı değiştirilir; `original` bytes veya raw record hâlâ eski değeri taşır.
- **Kanıt:** [PreservedLayoutTests.test_saved_candidate_rejects_independent_document_and_record_metadata_projection](../tests/test_native.py), `test_saved_candidate_rejects_forged_envelope_and_cached_identity` ve `test_original_source_projection_binding_remains_required` bu ayrışmaları sınar. `_preserved_byte_binding()` [native adapter](../src/universal_hmi/native/__init__.py) içindedir.
- **Kök neden ve karşı görüş:** Mutable parse nesnesi immutable dosyanın kanıtı değildir. “Document.bytes eşit veya owner SHA doğruysa cache'i güvenilir sayabiliriz” görüşü decoded metadata'nın raw kayıttan ayrılmasını ve detached envelope'u kaçırır.
- **Etki:** Guard onaylı kaynağın yerine bellekteki farklı projection'ı doğrulayabilir; record kimliği, family/model/raw version veya retained layout için sahte eşitlik oluşabilir.
- **Minimum düzeltme:** Immutable `original` bytes'tan envelope ve Document'i yeniden decode et; bütün mevcut projection/envelope/application/kimlik alanlarını bununla karşılaştır. Hem aday hem original source adapter coherency kontrolü geçmeden preserved layout doğrulanmaz.
- **Regresyon:** Named testler raw bytes değişmeden scalar `.value`/section `.name` değiştirmeyi; document substitution, thumbnail/prefix/body, family/model/version/application cache değişimini ve original-source projection ayrışmasını reddeder.
- **Rollback:** Kopmuş adapter/session kullanılmaz. Yetkili kaynak bytes'tan yeni adapter/session oluşturulur; metadata'yı değiştirilmiş cache'e göre yeniden hashleyerek kabul geri getirilmez.
- **Genellenebilirlik sınırı:** Fresh decode canonical byte bağını kurar; raw Order'ın z-order, thumbnail'ın güncel render veya opak offset'in vendor semantiğini kalibre etmez. Preserved nesneye yeni edit/clone/delete yetkisi vermez.

## C3 — Stat ile read arasında büyüme ve freshness okuması

- **Tetikleyici:** Metadata için `stat().st_size` küçük görünür, gerçek içerik okumadan önce büyür. Açılmış session'ın source/profile/calibration dosyası freshness kontrolünden önce büyütülür.
- **Kanıt:** [ExistingOwnerCandidateTests.test_actual_json_read_limit_rejects_artifacts_growing_after_stat](../tests/test_service.py) calibration ve approval için stale stat kurar; `test_freshness_uses_bounded_actual_reads_for_growing_inputs` üç session girdisinde gerçek read limitini ve typed changed kodunu denetler. `_json_object()` / `_fresh()` [service.py](../src/universal_hmi/service.py) içindedir.
- **Kök neden ve karşı görüş:** Stat snapshot'ı sonraki read'in boyutu değildir. “Önce stat ile limiti kontrol etmek yeterli” görüşü zaman aralığını ve sınırsız read maliyetini bırakır.
- **Etki:** Metadata sınırı aşılabilir; gereksiz bellek kullanımı oluşabilir veya stale sözleşme accepted sanılabilir.
- **Minimum düzeltme:** JSON metadata'nın **actual read**'ini 1 MiB + 1 byte ile sınırla ve limit aşımını typed hataya çevir. Freshness'te kaydedilmiş exact uzunluk + 1 byte oku; uzunluk ve SHA birlikte eşleşmelidir. Stat sonucu yetki veya boundedness kanıtı olarak kullanılmaz.
- **Regresyon:** Named testler stale stat'a rağmen calibration/approval'ın reddini; source/profile/calibration growth için `SOURCE_CHANGED`, `PROFILE_CHANGED`, `CALIBRATION_CHANGED` kodlarını ve tek bounded read boyutunu kontrol eder.
- **Rollback:** Değişmiş girdiyle apply/save devam etmez. Kaynağı küçültüp eski receipt'i zorla kullanma; yetkili yeni girdiyi aç, yeni kalibrasyon/plan ve gerekli insan onayını üret. Başarısız yeni output C1 sahiplik kuralıyla kaldırılır.
- **Genellenebilirlik sınırı:** Bu limit JSON metadata ve session freshness okumaları içindir; bütün native ilk okumaların, resim decompression'ın veya üçüncü taraf araçların genel kaynak limiti olarak sunulmaz. Dosya sistemi snapshot/lock garantisi değildir.

## C4 — Malformed profile yanlış hata kanalına düşüyor

- **Tetikleyici:** Profile JSON list/null/bozuk syntax, duplicate key veya nonfinite constant taşır; family, resolution, native_schema, capabilities veya model kimliği beklenen tipte değildir.
- **Kanıt:** [ExistingOwnerCandidateTests.test_malformed_profiles_are_typed_errors_and_neutral_labels_grant_no_vendor_authority](../tests/test_service.py) object olmayan ve malformed JSON ile hedef/mapping tiplerini sınar. `_json_object()` / `_profile()` ve `canonical_model_id()` [service](../src/universal_hmi/service.py) / [native identity](../src/universal_hmi/native/identity.py) içindedir.
- **Kök neden ve karşı görüş:** Parse başarıyla dönse bile JSON değeri profile sözleşmesi değildir. “json.loads sonrası `.get()` çağırmak yeterli” görüşü null/list'i, duplicate key'in sessiz son değerini ve yanlış scalar tiplerini kabul edebilir veya raw exception üretir.
- **Etki:** MCP kontrollü hatası yerine runtime exception oluşabilir; ambiguous metadata ile yanlış hedef veya kapsam yorumu yapılabilir.
- **Minimum düzeltme:** Bounded UTF-8 JSON object okuması; duplicate key/nonfinite reddi; profile ID, family, raw version, iki positive-int çözünürlük, capabilities/native_schema map ve model kimliğini açık typed doğrulama. Malformed profile structured `HmiError` ile kapanır, default hedef/mapping uydurulmaz.
- **Regresyon:** Named test malformed JSON çeşitlerini ve hedef/mapping scalar/container uyuşmazlıklarını reopened session'da reddeder. Eksik qualification metadata'sı typed hata üretir; “unsupported” etiketiyle başarıya dönüştürülmez.
- **Rollback:** Kaynak değişmez. Geçersiz profile kullanılmaz; yetkili exact kaynak için yeni profile/calibration revision'ı oluşturulur, değişmiş hash'ler için yeni plan/onay gerekir.
- **Genellenebilirlik sınırı:** İyi biçimli profile veya `qualified=true`, actual vendor/editor/model/driver kabulü değildir. Bu hata kanalı düzenlemesi full program-writer qualification'ı açmaz.

## C5 — Origin etiketi neutral onay yetkisi olmamalı

- **Tetikleyici:** Gerçek vendor kaynağı veya buna bağlı profil `original_neutral_fixture` / synthetic gibi etiketlenir ve `neutral_fixture_qualification` approval istisnası istenir.
- **Kanıt:** Aynı [ExistingOwnerCandidateTests.test_malformed_profiles_are_typed_errors_and_neutral_labels_grant_no_vendor_authority](../tests/test_service.py) forced neutral approval'ın `APPROVAL` ile reddini ve applied session'ın boş kalmasını kontrol eder. `_approval()` [service.py](../src/universal_hmi/service.py) içindedir.
- **Kök neden ve karşı görüş:** Provenance sınıflandırması insan tasarım onayı yerine geçmez. “Profil synthetic dedi, qualification istisnası uygundur” görüşü etiketin kullanıcı/vendor kaynağındaki raw kimlikten farklı olabileceğini kaçırır.
- **Etki:** Gerçek projeye insan onayı olmadan aday uygulanabilir; kaynak kökeni ve approval yetkisi birbirine karışır.
- **Minimum düzeltme:** Neutral istisnası birlikte actual native model `SYNTHETIC`, actual raw Version `0.0`, synthetic profile ve `purpose=qualification_only` ister. Diğer kaynaklar `authority=direct_human`, gerçek human_reference ve exact source/profile/design/bindings/operations/calibration receipt eşleşmesini ister.
- **Regresyon:** Named test etiketli ama actual neutral olmayan kaynağın forced approval'ını reddeder; bellekte applied candidate oluşturulmaz. Test fixture kökeni vendor uyumluluğu olarak sunulmaz.
- **Rollback:** Yanlış etiket/onay kullanılmaz; kaynak ve provenance gerçeğe göre düzeltilir. Mevcut receipt değiştirilerek onay taklit edilmez; yeni contract ve gerçek insan kararı kaydedilir.
- **Genellenebilirlik sınırı:** Raw SYNTHETIC/0.0 kontrolü mülkiyet/lisans araştırması değildir. Neutral fixture transaction testi gerçek model/editor/native görünüm, vendor compile/simulation veya fiziksel panel kabulünü kapatmaz.

## C6 — Değişmeyen geometri intent'i raw yazımı normalize ediyor

- **Tetikleyici:** Text-only veya no-op tasarımda kaynağın Y/Height gibi scalar'ları leading zero içerir. Sayısal IR değeri aynı olsa da writer bütün geometri alanlarını canonical decimal'e çevirir; X/Width değişikliğinde ara geometri sıfırlaması ilgisiz Y/Height'e de dokunabilir.
- **Kanıt:** [ExistingOwnerCandidateTests.test_caption_only_and_noop_preserve_padded_geometry_records](../tests/test_service.py), caption-only, değişmiş X ile diğer axis'in korunması ve exact byte no-op yollarını sınar. `_candidate_document()` / `_candidate_operations()` [service.py](../src/universal_hmi/service.py) içindedir.
- **Kök neden ve karşı görüş:** Aynı numeric değer aynı raw record değildir. “Her axis'i IR'dan tekrar yazmak tutarlı normalization sağlar” görüşü retained byte extent'ini daraltır ve kullanıcının değiştirmediği alanı değişiklik kapsamına alır. Sınırlar içinde kalmak için bütün axis'leri geçici sıfırlamak da gereğinden geniş mutation üretir.
- **Etki:** Geçerli caption-only/no-op plan gereksiz length hatasına düşebilir veya unrelated geometry bytes'ı değişebilir; kaynak koruma sözleşmesi bozulur.
- **Minimum düzeltme:** Pure beklenen dosyada numeric intent kaynak geometrisine eşitse record'a dokunma. Compiler yalnız gerçekten değişmiş position/size alanlarını yayımlar; resize/move sırasını mevcut konum + hedef boyut ve sayfa bounds'una göre seçer, başka axis'i normalize eden geçici reset üretmez. Değişmiş scalar için mevcut equal-byte-extent ve geometry validation sınırı korunur.
- **Regresyon:** Named test caption-only planın yalnız `set_text` ürettiğini; başka axis'teki padded raw Y/Height'in save/reopen'da aynı kaldığını, X-only değişimde de korunduğunu ve no-op operation listesi/whole source bytes eşitliğini kontrol eder. Güncel full run kabulü yukarıdaki C6 sonrası root raporuna bağlanır; eski 400-test snapshot'ı yeniden kullanılmaz.
- **Rollback:** Kaynak yeniden yazılmaz veya sıfırları temizlenmez. Hatalı candidate revision'ı teslim dışı bırakılır; immutable kaynakla yeni session/plan ve değişen contract için gerekli insan onayı oluşturulur. Failure output temizliği C1'in exact sahiplik kuralına tabidir.
- **Genellenebilirlik sınırı:** Bu değişiklik yalnız source-pinned mevcut caption/geometri adayındaki unchanged raw record korumasını ve bounded operation sırasını düzeltir. Padded scalar'a yeni encoding, geometry extent büyütme, font/layer/opaque offset veya vendor/panel semantiği qualification'ı vermez.

Bu düzeltmelerin ortak sınırı immutable kaynaktan kontrollü aday üretimidir. Yeni nesne/driver/macro/alarm/style üretimi ve iki ailenin tam V1 kabulü açık kalır; güncel aday kaynağının fresh relocation kabulü PENDING'dir. Taşınabilir yol tasarımı Linux/macOS çalışma kanıtı değildir.
