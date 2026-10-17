# DOP-B Headless V1 — 0.2.0

Bu sürümün teslim sınırı ayrı **DPS + kavramsal önizleme + doğrulama paketi**dir. Vendor derleme, native piksel eşitliği, PLC/panel yükleme ve fiziksel kabul bu sürümün çıktısı değildir. Güncel kapanış durumu [STATUS](../reports/headless/STATUS.json) içinde tutulur; bu planın varlığı READY anlamına gelmez.

## Mevcut yetenek sınırı

Yeni headless katman mevcut `FileService` üreticilerini çağırır. Dosya formatını veya yeni vendor alanını tahmin etmez. Varsayılan model profili tek başına üretim yetkisi değildir: gerçek boş hedef, donor kaynak, property witness ve proje-local kalibrasyon profili gerekir. Exact profil/driver/namespace/bit genişliği kapıları aynen kalır.

| Yol | Kabul edilmiş dosya kapsamı | Açık sınır |
|---|---|---|
| DOP-B10S615 blank/library | Dört buton türü, UINT giriş/gösterge, kaynakla bağlı yeni kontroller | Genel palet veya her B modeline destek değildir |
| Multipage | Ordinary sayfa, Türkçe literal, bit göstergesi, gezinme, mevcut kontrol üreticileri | Kaynak/auxiliary/layout sözleşmesi zorunlu |
| Driver | Kaynakla kalibre edilmiş DVP M/S/D, ayrı v2 X/Y radix sözleşmesi | Gerçek PLC adresinin varlığını veya fiziksel yazmayı kanıtlamaz |
| Numeric | Belgelenmiş UINT, explicit INT16/F0, kaynak display decimal ve existing integer yolları | TIME/64-bit/fractional input sessiz dönüştürülmez; desteklenmeyen kombinasyon reddedilir |
| Existing-owner | Kaynakla pinli görünüm/geometri/literal, inert silme, belirli entry permission | Unknown nesne ve bağımlılıklar korunur; tam program üretimi değildir |
| Alarm/macro | Mevcut ayrı kaynak/sözleşme kapıları | Yeni arbitrary external macro operand veya tüm alarm lifecycle/retention desteği eklenmedi |

Sıcaklık projesindeki R011/R012 yalnız proje adaylarını değiştirmiştir; genel MCP koduna yeni yetenek getirmemiştir. Özel proje, tag, logo ve dosya yolları bu sürüme alınmaz. R010 fractional giriş deneyi genel kabul olarak taşınmaz.

## Güven sınırı ve kurulum

[Kurulum](HEADLESS_INSTALL.md) Windows x64 ve Ubuntu x86_64 için sabit sürüm/hash ile kullanıcı klasöründe çalışma ortamı kurar. Runtime, MCP, profil ve template kaynakları paketin içindedir; Git veya Delta IDE çalıştırılmaz. Çevrimdışı pakette runtime ve bütün platform wheel'leri bulunur. Eksik yazılım resmî, sabitlenmiş kaynaktan kurulabilir. Fiziksel donanım indirilemez; sürücü yazılımıyla karıştırılmaz. Admin/lisans/eksik fiziksel cihaz, kapsamı aşan sessiz işlem yerine açık engel kaydı üretir.

Başlatıcı güvenilen `task-policy.json` dosyasını **iş girdisinin dışında** kurar. Modelin gönderdiği `job` JSON'u policy kuramaz/değiştiremez. Policy; kaynak hash'lerini, profil paketini, izinli işlemleri, çalışma/teslim/denetim köklerini, süre ve byte bütçesini, yazar ve bağımsız denetmen kimliklerini sınırlar. İş, dosya erişimi olan ajan için OS sandbox değildir. Aynı OS hesabıyla policy/state yazabilen kötü niyetli süreç tehdit modelinin dışındadır; üretimde başlatıcı ve denetmen dizinlerine OS izinlerini ayrı uygula.

Genel MCP paketi vendor donor içermez. Yetkili referanslar `reference_pack.create_pack` ile explicit allowlist ve hak kaydı üzerinden ayrı taşınır; `import_pack` dış güvenilen kanaldan gelen arşiv SHA'sını doğrular. ZIP içindeki provenance kendi kendine lisans/kimlik kanıtı değildir. Aynı bayt snapshot'ı hashlenip açılır; path traversal, link, case collision, aşırı boyut ve dosya listesi farkı reddedilir.

## Tek yetkiyle uçtan uca workflow

1. **Başlat:** görev kapsamı ve referans/profil paketini sabitle. Yazar ve teknik + iki sıralı estetik denetmen ata. Policy'yi başlatıcı kurar; kullanıcı görev başlangıcında yetki verir.
2. **Preflight:** `preflight_job` gerçek kaynağı açar, mevcut üreticiyle plan oluşturur, feature/type/address/geometri ve kalibrasyon tazeliğini doğrular. Eksik/unsupported veri daha teslim başlamadan hata verir.
3. **Kuyruk:** `submit_job` idempotency key + tam job sözleşmesini SQLite'a kaydeder. Aynı key/aynı içerik aynı işi döndürür; farklı içerik conflict olur. Tek aktif lease; süreç ölümü sonrası expired lease sahiplenilir.
4. **Tasarım incelemesi:** teknik plan → ilk estetik → ikinci estetik. İkinci rapor ilk estetik rapor SHA'sını taşır. Başlatıcının ajanları state içindeki `*.review-request.json` dosyasını okur, exact subject üzerinde inceler, raporu yalnız güvenilen reviews dizinine koyar. İlk modelin kendine PASS yazması kabul değildir.
5. **Üret:** dört kontrol hash'ine ve task authority'ye bağlı plan ayrı çalışma dosyasına uygulanır. Native dosya yeniden okunur ve mevcut bağımsız IR karşılaştırmalarından geçer. Final teknik denetim native candidate SHA + diff ve önceki estetik rapora bağlıdır.
6. **Yayımla:** exact sekiz içerik dosyası doğrulanır. Manifest SHA'sı ayrı güvenilen SQLite state'e pinlenir; ardından lease/cancel ile aynı transaction altında no-replace klasör yayını ve completion yapılır. İş bu commit noktasına girdiyse cancel `JOB_PUBLICATION_PENDING` verir. Yeni üretim yerine yalnız aynı pinin recovery'si yapılabilir.
7. **Teslim:** `job_result` paketi ve güncel denetimleri tekrar doğrular. Başarı `OFFLINE_DELIVERY_COMPLETE` olur; vendor/native_visual/physical ayrı `NOT_RUN` kalır. DPA veya farklı modele dönüştürme yapılmaz.

Eksik inceleme `WAITING_REVIEWS` olur; ara insan onayı istenmez. İncelemeleri oluşturacak ajan orkestratörü MCP çağırıcısıdır; kütüphane kendi LLM hesabı/anahtarı veya reviewer süreci uydurmaz. `submit_job` sabit paket worker'ını başlatır; dispatcher review dosyası değiştiğinde otomatik devam eder. Yapılandırılmış MCP yeniden başladığında bitmemiş kuyruk için dispatcher otomatik başlar; yeniden submit gerekmez. Host servis yöneticisi ayrıca `dispatch-jobs --policy ... --state ...` ile aynı kuyruğu sürdürebilir. 24 saat hiç ilerleme olmazsa dispatcher çıkar; kalıcı kuyruk kaybolmaz, host servis yöneticisi yeniden başlatabilir.

CLI `run-job` ve MCP worker'ları sabit alt süreçte toplam aktif süreyle sınırlanır. Review bekleme süresi aktif bütçeden sayılmaz. Uzun parser işlemi supervisor tarafından sonlandırılır. Python içindeki `run` primitive'i yalnız test/worker içindir. Kalıcı pin sonrası bozulma yeni üretimle örtülmez; `RECOVERY_BLOCKED` teşhisi ve mevcut dosyalar korunur. Process-crash recovery test edilir. Windows/depoma donanımına karşı ani elektrik kesintisinde fiziksel disk kalıcılığı garanti edilmez.

## API ve kullanım

Eski dokuz araç değişmez. `serve --job-policy <trusted-policy> --job-state <private-state>` ile beş araç eklenir: `preflight_job`, `submit_job`, `job_status`, `job_result`, `cancel_job`. Native file-service araçları task authority'yi otomatik devralmaz; legacy exact insan onayı/neutral fixture kuralları kalır.

```text
python -m universal_hmi.cli preflight-job --policy HOST_POLICY --state STATE --input JOB_JSON
python -m universal_hmi.cli run-job --policy HOST_POLICY --state STATE --input JOB_JSON --key TASK_KEY
python -m universal_hmi.cli dispatch-jobs --policy HOST_POLICY --state STATE
python -m universal_hmi.cli job-result --policy HOST_POLICY --state STATE --job-id JOB_ID
```

CLI exit 0 başarılı işlem, 2 FAILED/CANCELLED/hata, 3 WAITING_REVIEWS. İnceleme yokken boş `PASS` raporu üretmek yasaktır. Unit test içindeki TEST ONLY raporları bu protokolün test verisidir; gerçek bağımsız kabul değildir.

## Goals ve kapanış kapıları

| Goal | Sahip | Girdi | Kapanış kanıtı |
|---|---|---|---|
| H0 Kapsam/otorite | Orkestratör | Onaylı plan, eski baseline | Ayrı policy transition commit, epoch, envelope, checkpoint |
| H1 Taşınabilir runtime | Paket uygulayıcısı | Sabit dependency/runtime lock | Temiz klasörde Windows/Linux kurulum, wheel kaynakları, offline test |
| H2 Kalıcı işler | Uygulayıcı + teknik denetmen | Policy/job/review sözleşmeleri | Restart, kill, budget, source change, cancel/publish ve sahte paket negatifleri |
| H3 Üretim entegrasyonu | Uygulayıcı | Yetkili B referans paketi | Gerçek stdio/CLI job, native yeniden okuma, kaynak eşitliği |
| H4 Bağımsız kabul | Teknik + iki estetik denetmen | Exact plan, üç preview (0/1/geçersiz), aday | Hash'e bağlı raporlar, açık önemli bulgu yok |
| H5 Nihai paket | Orkestratör | H0–H4 | Manifest, destek matrisi, kurulabilir ZIP/wheel, scoped commit |

Bu goals önceki iki-aile V1 goals yerine geçmez. Hedeflerin açık durumu checkpoint ve STATUS'ta saklanır. Aynı hata düzeltilmeden PASS aktarılmaz; kaynak değişirse ilgili test/denetim tekrar edilir.
