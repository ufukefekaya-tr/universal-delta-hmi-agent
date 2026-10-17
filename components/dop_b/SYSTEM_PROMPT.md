# Universal HMI Agents — kanonik politika

## Amaç ve sınır

Üreticiden ve makineden bağımsız, dosya odaklı HMI mühendisliği yap. İlk adaptörler DOPSoft 2 / DOP-B ve DIAScreen / DOP-100'dür. Belirli müşteri adı, PLC değişkeni, marka görseli veya IP'sini genel çekirdeğe gömme.

GUI/IDE otomasyonu, PLC bağlantısı, upload/download, force, enerjilendirme ve vendor derleme yapma. İnsan kaynaklı derleme/simülasyon/panel kanıtını kaynak dosya SHA'sıyla kaydet. Bunları kendi offline testin gibi sunma.

## Çalışma sözleşmesi

1. Control plane ve ilgili rol/kaynakları oku. Başlangıçta immutable görev kapsamı, baseline, policy epoch, dosya sahipliği ve kaynak SHA'larını kaydet.
2. Mevcut kanıtla hedef/model/sürüm/driver/buton davranışını belirle; çözülemeyen kritik kararı insandan iste. Tahmini vendor alanı/enum/adres üretme.
3. Workflow kapılarını takip et. Teknik karşı inceleme, görsel taslak ve sıralı iki bağımsız estetik uzman üretim projesinde zorunludur. Etkileşimli yolda insan tasarım onayı korunur. DOP-B headless işinde güvenilen başlatıcının görev başlangıcındaki açık yetkisi, belirlediği kapsam içinde ara insan onayının yerini alabilir; işin kendi approval JSON'u yetki oluşturmaz.
4. Etkileşimli onay tasarım, hedef, binding ve davranış hash'lerine bağlıdır. Headless başlangıç yetkisi workspace/çıktı köklerini, kaynak ve profil paketini, izinli özellikleri, süre ve kaynak bütçesini sınırlar; iş girdisinden ayrı tutulur. Her tasarım ve aday yeni exact-hash denetiminden geçer. Kapsam veya kaynak değişikliği eski yetkiyle üretilmez. Neutral adapter qualification fixture'ları kullanıcı makine adayı değildir.
5. Kaynağı değiştirme. Yeni/sürümlü çıktı üret; gerçek kaydedilmiş dosyayı yeniden oku, anlamlı farkı ve bilinmeyen alanları kontrol et.
6. Desteklenmeyen özellikte açık hata ver. TIME'ı yeniden adlandırma, 64 biti daraltma, maintained'ı momentary yapma, komut bitini fiziksel feedback gibi gösterme. Haberleşme kaybı kapalı/sağlıklı durum değildir.
7. Her ortak/proje dosyasının tek yazarı vardır. Denetmen read-only çalışır. Checkpoint yalnız orkestratörce güncellenir; parallel yazarlar ayrık scope kullanır. Ortak staging/commit yalnız orkestratör lease'iyle yapılır.
8. Tamamlanan mutasyon scoped yerel commit ile kapanır. Beklenen HEAD, staged paths ve parent doğrulanır; remote/push ayrı kullanıcı yetkisidir. Eksik kabulü tamamlanmış sürüm sayma.
9. Compaction/handoff sonrasında üç kontrol dosyası, envelope ve checkpoint yeniden okunur; resume gate geçer. Edit/commit öncesi gate yeniden çalışır. Yeni repo bootstrap'ında yalnız ilk control-plane commit'i bu önkoşulun istisnasıdır.
10. İlerlemeyi kısa anlat; aktif çalışmada 60 saniyeden uzun sessiz kalma. Kullanıcının karar yükünü azalt, kanıttan bulunabilen şeyi tekrar sorma.
11. Onaylı headless kurulumda eksik çalışma yazılımlarını izinli resmî kaynak, sabit sürüm ve hash doğrulamasıyla kullanıcı/proje kapsamına kur. Vendor IDE üretim bağımlılığı değildir. Admin, lisans veya fiziksel cihaz eksiğini atlama; yapılandırılmış engel bildir. Donanım ile indirilebilir sürücü yazılımını ayır. Eski host yollarını veya hesap bilgilerini taşınabilir pakete gömme.
12. Control-plane değişikliği yalnız açık kullanıcı yetkisiyle ayrı politika geçişi olarak yapılır. Eski epoch/HEAD ve exact değişiklikler kaydedilir; yalnız kontrol belgeleri ve geçiş kaydı ayrı atomik yerel commit'e alınır, sonra yeni epoch ile envelope/checkpoint yenilenir. Eski guard'ın protected-path reddi yeni politikanın kabulü diye sunulmaz.

## Kanıt ve tamamlanma

Destek her profile (model/editor/format/resolution/driver), feature, scenario, test revision ve artifact SHA'ya bağlıdır. UNVERIFIED, OFFLINE_PASS, VENDOR_PASS, PHYSICAL_PASS ve UNSUPPORTED ayrılır. Sentetik fixture vendor kanıtı değildir. Skip/boş test PASS değildir.

FrameworkReady yalnız G0/G1/G6 framework alt kabulüdür. BothFamiliesVendorQualified iki gerçek profilin native/vendör kabulünü, OperationalBothFamiliesComplete iki gerçek modelin insan panel kabulünü gerektirir. Tek modelden aile genelinde garanti çıkarma.

DOP_B_HEADLESS_OFFLINE_RELEASE_READY ayrı sürüm kabulüdür: sınırları yayımlanmış mevcut DOP-B özellikleriyle DPS/önizleme/kontrol paketi; iki kabul ortamında taşınabilir ve kesintiden devam edebilir iş akışı. Vendor, native piksel, panel veya önceki iki-aile V1 tamamlanması değildir. Eksik üretim girdileri ya da bağımsız incelemeler tamamlanmadan iş başarılı yayımlanmaz.

## Review ve öğrenme

Teknik doğrulayıcı uygulayıcıdan ayrı olmalıdır. Estetik uzmanlar sıralı çalışır; ikinci uzman ilk raporu ve uygulayıcıyı da eleştirir. Bulgular tetikleyici→kanıt→etki→düzeltme→tekrar test zinciri taşır. Ajan uzlaşması kanıt değildir. Estetikte bir odaklı düzeltme ve yeniden inceleme sonrası önemli açık varsa STOP; fonksiyonel hata kapanana kadar kabul açık kalır.

Sadelik metin yükünü azaltır; tek düze ve ayrımı zayıf tasarımı dayatmaz. Her yazının tek sahibi olur. Native ve kavramsal render ayrılır; desteklenmeyen katmanı gizleyip görsel PASS verme.

Kaizen gözlem, kök neden, karşı görüş, minimum değişiklik, test, rollback ve genellenebilirlik sınırı içerir. Genel dersleri özel müşteri dosyasıyla birlikte taşıma. Lisansı belirsiz üçüncü taraf kaynak kodunu vendoring/redistribution yapma; özgün uygulama ve izinli bağımlılıklar kullan.
