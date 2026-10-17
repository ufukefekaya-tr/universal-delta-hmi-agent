# Mevcut programı dosyadan düzenleme — uygulama kapıları

Bu belge sıradaki genel V1 geliştirmesinin planıdır. Public MCP'de bu bütün yol **henüz yoktur**; eski library/calibration üzerinde SHA veya qualified bayrağı değiştirerek açılmaz. [Araştırma](../reports/PRESERVED_PROGRAM_RESEARCH.json) statik kaynakla sınırları ayırır; test/derleme/görsel kabulü vermez.

Amaç, mevcut programdaki onaylı görünüm ve adres sözleşmesini ayrı aday dosyaya uygulamaktır. Müşteri projesi, logo, tag, özel tasarım veya sabit bilgisayar yolu çekirdeğe taşınmaz. Kaynağı uygulayan proje ajanı kendi tasarım onayını ve private kaynaklarını yönetir.

## Birlikte kapanacak işler

| İş | Sözleşme | Kapı |
|---|---|---|
| Mevcut nesneler | Exact kaynak/family/model/version/owner/state pins; geometri/font ve doğrulanmış görünüm alanları | İlk scalar kapsam aynı original kayıt uzunluğunu korur; diğer adres/numeric/macro/keypad/navigation/metadata byte'ları kaynakla aynı |
| Sabit içerik silme | Yalnız açıkça seçilmiş inert Type10/Sub6; grup/macro/ref graph sınırı | Canlı nesne, kimlik, sayfa ve kaynak sırası korunur; bilinmeyen ilişki açık hata |
| Görünüm | Numeric flat nativeStyle0; text-only nativeStyle3; Type/SubType/Style bazında gerçek renk rolleri | Runtime16 native dosyaya yazılmaz; alpha/flat-filled-button kabulü uydurulmaz |
| Font | Size ve Ratio ayrı alanlardır; family/align/style companions exact | Ratio0/48→100 otomatik normalizasyon yok; Size=0 veya CSSpx eşdeğerliği varsayılmaz |
| Arka plan | Mevcut tekil sayfa bağlantısında aynı boyutlu opak PNG→DIB piksel değişimi | İç bitmap başlıkları, offset graph ve kanal/satır yönü doğrulanır; ham PNG yazılmaz |
| Ondalıklı sayı | INT16 F1/F4 raw/display ve signed input limitleri ayrı doğrulanır | Compiler/keypad truncation sorunu kapanmadan input açılmaz; epsilon veya sessiz tip değişikliği yok |
| Veri ve yazma izinleri | Kaynakta yetkili kalite flag'i ve açık configurable interlock ilişkisi | Eski veri sağlıklı/kapalı görünmez; engelli yazıma izin verilmez; sabit müşteri bitleri core'a gömülmez |

İlk mevcut-nesne scalar kapsamı her değişen kaydın raw byte uzunluğunu korur. Uzunluğu değiştiren istek ayrı framing/ref proof kapanmadan reddedilir; padding, sessiz normalizasyon veya başka alanı kaydırarak gizlenmez. Sabit owner silme kendi graph kapısını ayrıca geçer; scalar alanların uzunluk sınırını otomatik kaldırmaz.

Mevcut signed/ondalıklı sayı yalnız taşınacaksa numeric factory ile yeniden üretilmez. O alanlar kaynakta opaque ve byte-exact tutulur. Numeric davranışı değiştirilecekse ayrıca typed numeric sözleşmesi gerekir. Yapısal `preserved_layout` PASS, davranışın korunduğunu tek başına kanıtlamaz.

## Uygulama sırası

1. Primary kaynaklar ve gerçek dosya şekli karşı incelemeden geçirilir; exact scope/tek yazar/checkpoint kaydedilir.
2. Registered factual contracts, bounded parser ve kaynakla sabitlenmiş calibration helper geliştirilir. Desteksiz şekiller typed hata verir.
3. Ortak niyet modeli, bağımsız expected-body üretimi ve mevcut dokuz MCP aracı bütünleştirilir. Plan değişirse eski onay geçersizdir.
4. Tarafsız, özel varlık içermeyen fixture ve bağımsız negatif örnekler kullanılır. Gerçek private kaynaklar proje-local kalır.
5. Fresh SDK oturumu plan→önizleme→doğrulama→yetkili onay→uygula→yeni kayıt→yeniden oku→fark akışını tamamlar. Tekrar çağrı/başka proje/kaynak veya asset drift'i sınanır.
6. Gerçek saved body kaynak+tam izinli değişikliklerden ayrı kurulmuş body ile aynı olmalıdır. Eski alan/pikseller geri konunca bütün kaynak body geri gelmelidir.
7. Bağımsız son denetim, kapsam/sürüm/hash/destek matrisi ve scoped yerel commit tamamlanır. Alt özellik PASS'leri bütün paket hazır hükmü değildir.
8. Paket tamamlanınca yetkili proje ajanına tek hazır bildirimi gönderilir; o ajan kendi onaylı tasarımını topluca uygular. Önemli ve dosya/statik yöntemle kapanamayan bir engel varsa tek somut bildirim yapılır.

Vendor/native pixels/simülasyon/panel kabulü insan testinde ayrıca dosya SHA'sına bağlanır. Bu geliştirme bilgisayar kontrolü veya IDE/PLC işlemi kullanmaz. Tam V1 ve iki aile kabulü açık kalır; bu plan bunları kapatmaz.
