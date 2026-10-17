# DIAScreen bağımsız adres ve yeni program yolu

Bu işin hedefi, ortak ekran tanımından yeni adreslerle bağımsız DIAScreen programı üretmektir. Kaynak kontrolü eski adresiyle kopyalamak bu hedefi karşılamaz. Şu an eklenen `DiaScreenAddressNamespace`, bu üretim yolunun saf adres doğrulama temelidir; native dosya üretmez ve public MCP kontrol capability'si açmaz. Yeni kodun bağımsız kabulü ve güncel 894-test regresyonu geçti; [araştırma kaydı](../reports/DIASCREEN_AS_ADDRESS_RESEARCH.json) bu sınırlı offline kabulü taşır. Önceki880-test kayıtları kendi revision'larıyla korunur.

## Kanıtlı adres temeli

Kurulu tarafsız Temperature_Control_Demo kaynağında Delta AS series PLC TCP, `EtherLink1`, station1, native controller index1 ve native link2 gözlenmiştir. Link2 değeri controller sıra numarasından hesaplanmaz; doğrudan kaynak owner alanlarıyla doğrulanır. Kaynak model268502784, serialized6.0.00209.8338'dir. Seçilmiş110IS veya başka model kabulü değildir.

İlk ayrı sözleşme yalnız canonical scalar decimal BOOL `M0..8191` ve UINT `D0..29999` adreslerini içerir. Sürücünün statik tabloları ve resmi AS cihaz tablosu bu aralıkları doğrular. Dotted `D.n/X.n/Y.n`, özel/sistem alanları, REAL/LREAL/TIME ve yeni driver ayarları bu primitive ile açılmaz. Kaynak geniş aralık kullandığı için her CPU'nun belleği veya her makinenin yazma yetkisi otomatik kabul edilmiş sayılmaz.

`source`, descriptor ve raw authority immutable snapshot'tır. Model/version/source SHA, tam driver span SHA, channel/station, native link ve her storage domain'i için ayrı aktif read/write witness'ı kontrol edilir. Witness; exact page/ID, bütün Element+States SHA, address, native link, `MemType=0`, BOOL0/2 veya UINT1/2 width/format alanlarını doğrular. Authority JSON hash eşitliğinin yanı sıra family/version/driver/region metadata eşitliği gerekir. Caller dict değişikliği veya dönen metadata'yı değiştirmek snapshot'ı değiştirmez. Descriptor tek başına üretici kökenini, incelemenin yapıldığını veya machine authorization'ı kanıtlamaz.

Bu primitive source dosyasını açıp izlemeyi sürdürmez. Public transaction her işlem ve kayıt öncesinde dosya, profil, authority ve design hash'lerini tekrar okumalıdır. Mevcut B v1/v2 adres parser'ı değiştirilmedi. Bu ayrı DIA sınıfı, `AddressNamespace` veya eski calibration flag'i üzerinden gizlice kullanılamaz.

## Tam üretim için kalan geçişler

1. **Kaynak ve authority:** adres ve sürücü tablosu, source witness'ları ve bağımsız negatif denetim tamamlanır. Source-control klonlama ve yeni adres lowering ayrı kayıt taşır.
2. **Mantıksal kontrol lowering:** ordinary IR read/write/storage/direction ile doğrudan native alanlar eşlenir. Momentary, maintained, set-on/set-off, indicator, input/display için davranış ve read policy ayrıca kanıtlanır. Numeric `ReadMemType=3` için tahmini fallback kullanılmaz. Tetikleme, görünürlük, interlock, unit veya makro bağları yeni programda örtülü bırakılamaz; korunacak bağlar IR'de açık olur veya kaldırma dönüşümü ayrı kaynakla doğrulanır.
3. **Temiz hedef ve ayrı kütüphane:** gerçekten bağımsız, sıfır-owner, kanıtlı global macro/driver/alarm/resource baseline'ı olan hedef ve immutable typed library gerekir. Kurulu22 örnekte zero-owner sayfa bulunmadı. Demo owner'larını silmek temiz hedef üretmez: Temperature InitialMacro6478, page2 OpenMacro379, CycleMacro931 byte ve ScreenAction250 içerir. Bunların sessizce kalması veya tahmini sıfırlanması kabul edilemez. Başlangıç alanlarının üretici oluşturma/okuma/yazma sözleşmesi veya gerçek boş vendor girdisi doğrulanmalıdır.
4. **Program birleştirme:** page/text/Türkçe caption/font/indicator/goto, numeric width/limits/scale/unit, startup/periodic/button macro, alarm strip/current/history aynı onaylı IR transaction'ında birleştirilir. Library global verisi hedefe taşınmaz; bilinmeyen alanlar kontrollü korunur. Kaynak-driver ve resource tüketim zinciri ayrı doğrulanır.
5. **MCP akışı:** ayrı portable registry/calibration ve yeni-only save_as; source/profile/authority/design/binding/operations onay hash'leri; saved whole-BODY'nin emitter'dan bağımsız oracle ile eşitliği, kaynak restorasyonu, replay/no-op, sessions/idempotency/freshness ve iki proje izolasyonu sınanır. Eski driver veya clone capability'si genişletilmiş gibi gösterilmez.
6. **Kullanıcı makine tasarımı:** sürümlü önizleme, teknik denetim, sıralı iki estetik denetim ve gerçek insan onayı gerekir. Adaptörün tarafsız development fixture yetkisi makine tasarım onayı değildir.
7. **Gerçek kabul:** iki ailede ortak tarafsız pilotlar ve exact aday SHA'larına bağlı insan vendor/uygulanabilir simülasyon/panel kabulü tamamlanır. Dosya parse veya adres tablosu sonucu bu kapıların yerine geçmez.

Bu adımlar tamamlanana kadar geniş G2/G3/G4 ve full program writer/V1 açık kalır. Computer Use, vendor DLL çalıştırma, IDE otomasyonu, PLC bağlantısı ve panel yükleme yapılmaz. Kaynak kurulum yolu, özel IP/credentials veya üretici proje/varlıkları çekirdeğe dağıtılmaz.
