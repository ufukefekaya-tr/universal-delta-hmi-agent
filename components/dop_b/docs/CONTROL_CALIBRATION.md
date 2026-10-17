# Komut, sayı ve sürücü kalibrasyonu

Bu aşama dosyadan ölçülen alanları toplar. Buton davranışını, veri tipini veya PLC yazma yetkisini kendiliğinden doğrulamaz. Genel repo hiçbir vendor dosyasına veya yazar bilgisayarının yoluna bağlı değildir.

## Kaynak kaydı

Yetkili yeni proje girdisini kendi workspace'inin `inputs/` dizinine koy. DOPSoft 2 için gerçek DOP-B `.dps`, DIAScreen için `.dpa` kullan; HMC veya dönüştürülmüş DOP-100 dosyası B kabulü değildir. Kaynağın kökeni ve izinleri proje içinde kalır. Referans modeli kullanıcıya tekrar seçtirmek gerekmez; test modeli araştırma sırasında seçilebilir.

```text
python scripts/capture_controls.py --workspace "projects/<project>" --source "inputs/reference.dps" --family delta_dopsoft2 --output "evidence/control_capture_v001.json"
```

DIAScreen'de family `delta_diascreen`, kaynak uzantısı `.dpa` olur. Komut herhangi bir çalışma dizininden, bu checkout'a kurulmuş Python ortamıyla çalışır. Çıktı yalnız yeni JSON'dur; kaynak değiştirilmez, native aday ve onay oluşturulmaz. Var olan çıktı üzerine yazılmaz. Kaynak yeni çıktı oluşturulmadan değişirse kayıt durur. Çıktı oluşturulduktan sonra değişirse işlem `SOURCE_CHANGED / capture_acceptance=FAIL` döner; `UNVERIFIED` gözlem dosyası korunur ve yeni revision gerekir. Başka bir yazarın aynı path'e koyduğu dosyayı silme riski alınmaz.

MCP `inspect` aynı kaynağın kompakt kontrol/sürücü gözlemlerini verir. Tam owner/global kayıtları bu araçla alınır. Kaynak değişince oturum yeniden açılır. Gözlem limiti aşılırsa `CALIBRATION_LIMIT` raporlanır; boş gözlem PASS sayılmaz.

Kayıtlar kaynak SHA'sını, ham model/sürümü, owner ve global bölüm hash'lerini, gözlenen sayısal alanları, adresleri, sürücü blok sınırlarını ve opak zarf hash'lerini taşır. Tekrarlı alanlar ve hatalı/tekrarlı controller işaretleri görünürdür. Başlık, açıklama, makro ve resim payload'ları dışa aktarılmaz. Anahtarı hassas bilgi belirten kayıtlar redakte edilir. Çıktı yine proje verisidir; genel repoya eklenmez.

## Üretim yetkisini açacak ayrı kanıt

[Kontrol kalibrasyon şablonunu](../templates/CONTROL_CALIBRATION.json) proje içine kopyala. Şablon uygulanan native schema veya onay değildir; doldurulmuş olması tek başına yetki vermez.

Her hedef/editor/driver kombinasyonu için şu ilişkiler bağımsız olarak kanıtlanmalıdır:

| Alan | Gerekli kanıt |
|---|---|
| Dört buton türü | Vendor özellik kaydıyla exact owner eşleşmesi; tür dışında aynı kontrollü girdinin before/after dosya farkı; başlangıç 0 ve 1 için basma/bırakma sonucu |
| Sayı | Vendor bit genişliği/format/işaret/ondalık ayarı; exact Read/Write, MemLen/MemFmt ve companion alan eşlemesi; alt/üst sınır ve ölçek |
| PLC bağlantısı | Driver/link/istasyon/adres grameri; yetkili Read/Write kataloğu; byte/word sırası; global kontrol ve durum adreslerinin sahipliği |
| Makro ve alarm | Native owner, tetikleyici, operand, zamanlama ve kayıt/retention ilişkileri; salt metin veya field presence yeterli değildir |
| Native kayıt | Bağımsız holdout dosyası, kontrollü fark, yeniden okuma ve exact SHA'ya bağlı insan vendor testi |

Momentary davranışı için ilk değeri mutlaka sınayın: bazı sözleşmeler basmada mevcut değeri tersler, bırakmada ilk değeri geri getirir. Başlangıç 1 durumunu hiç sınamadan "bırakınca 0" kuralı üretmeyin. Maintained seçimin komut isteği ile kabul edilmiş PLC modu ayrı tutulur. Bağlantı kaybı kapalı/sağlıklı olarak gösterilmez.

Açıklamada `Momentary` veya `Maintained` yazması native enum kanıtı değildir. Sadece pozitif limitli numeric örnek signed/unsigned ayrımını kanıtlamaz. Reçete belleğindeki sayı donor'ı dış PLC adresinin yerine geçmez. Kaynaktaki global adresin flag'i 0 diye başka makineye taşınabileceğini varsaymayın.

Teknik denetmen ham dosyayı, property kanıtını ve bağımsız holdout'u salt okunur inceler. Eşleme kapanmadan ilgili üretim özelliği `UNVERIFIED` kalır. Kullanıcının makine adayı ayrıca önizleme onayından sonra üretilir; gözlem aracı bu kapıyı atlamaz.

## Yeni kontrol üretimi

Altı ayrı gerçek vendor owner'ı ve exact property görüntüleriyle kalibre edilen kaynak için [kontrol üretimi](CONTROL_GENERATION.md) uygulanabilir. Bu stored-configuration modu yalnız mevcut sayfalara yeni dört buton ve UINT input/display ekler; original owner'lar korunur. Source SHA, native şekil ve görüntü hash'leri public apply/save kapılarında yeniden kontrol edilir. Bu yol basma/bırakma, driver veya panel kabulünü otomatik kapatmaz.

## Mevcut açık iş

Public B örnekleri tek başına dört türün vendor property eşlemesini ve typed external numeric donor'ını birlikte sağlamadı. Kullanıcının yetkili tarafsız B10S615 kaynağından altı özellik örneği kaydedildi ve MCP'den ayrı aday üretildi. Bu kaynak diğer seçilmiş modellere veya bütün aileye kabul vermez. İncelenen DIAScreen full demo internal/recipe örneklerini içeriyor; bunlar dış sürücü kabulü değildir. Tam DOP-B/DOP-100 program yazarı, G2/G3/G4 ve insan G5/G7 kabulleri açık kalır. [Güncel B durumu](../reports/DOP_B_READINESS.md).
