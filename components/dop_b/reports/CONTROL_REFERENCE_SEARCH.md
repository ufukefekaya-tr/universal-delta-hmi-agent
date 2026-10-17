# DOP-B kontrol referansı arama sonucu

Uygulama için gereken native davranış/tip eşlemesini bulmak üzere üretici örnekleri, kurulu üretici konfigürasyonları ve program yazarlarının immutable Git kaynakları salt okunur incelendi. [Exact kaynak/hash kayıtları](CONTROL_REFERENCE_SEARCH.json). Native dosya, görsel veya üçüncü taraf kod repo'ya kopyalanmadı; vendor uygulaması çalıştırılmadı.

| Kaynak | Somut bulgu | Üretim için kalan kanıt |
|---|---|---|
| Yazarın B03E211 dosing `.dps` projesi | 9 sayfa/94 owner;12 Type1/Sub4,3 Type1/Sub3,4 Type5/Sub1 | Type1/Sub1–2 ve numeric input yok; alias/driver ve description dışı tür kanıtı yok |
| Yazarın eski B07E515 Modbus `.dps` projesi | Gerçek B zarfı;21 legacy Element; numeric display ve Type1/Sub5 | nPartsID yok; dört temel bit butonu yerine multistate nesneleri var; yeni native kimlik uydurulamaz |
| Yazarın DOP-107WV `.dpa` projesi; raw Version4.00.16.30 | Haricî `{Link2}1@D1` numeric entry; MemLen1/MemFmt2/0…9999 | Gerçek üretici executable/build'i doğrulanmadı; DOP-B veya zorunlu DIAScreen profil kanıtı değildir; primitive width/format ve yazma yetkisi property/driver kanıtıyla kapanmamış |
| Üretici DOPSoft2 PanelList | B07S411 kimliği2953265424,800×480 doğrulandı | Model kimliği nesne davranışı veya vendor compile kabulü değildir |
| Üretici HMI–DTC ZIP | Yalnız eski `.dpb` üyesi | DPS2 referansı değildir |
| Distributor DOP example ZIP | Kamuya açık link, fetch403 | Erişim aşılmadı; dosya görülmedi, kabul üretilmedi |

Yeni kaynaklar buton/sayı adaylarına ilişkin araştırmayı genişletiyor. **Tam dört B buton davranışı ile PLC numeric tipleri henüz kalibre edilmedi.** `Maintained_…`/`Momentary_…` description, positive limit veya adres varlığı tek başına bu boşluğu kapatmaz. MemType farkı, tag alias veya resim/macro bağımlılığı aynı driver/model/editor kabulü olmadan sadeleştirilemez.

İlerlemek için bir kerelik vendor-created B referansı gerekir: aynı hedef/editor/driver üzerinde SetOn, SetOff, Momentary, Maintained ve PLC'ye bağlı numeric input/display nesneleri; exact source SHA ve vendor property/owner eşlemesi. [Gerekli kanıt listesi](../docs/CONTROL_CALIBRATION.md). Test modeli kullanıcıya tekrar seçtirilmez. Mevcut/source-local literal adaylarının çalışması tam kontrol üretimi kabulü değildir.

Bu aşamada executable kod ve42-source revision değişmedi;456-test kabulü aynı koda aittir. Araştırma bir test veya native üretim PASS değildir. Full V1/G2/G3/G4 ve insan G5/G7 açık kalır.

Bağımsız salt-okunur denetmen üç immutable dosyanın SHA'larını ve sayfa/owner/tür sayılarını yeniden üretti. B kaynakları hâlâ dört tür/property ve typed external input ilişkisini sağlamıyor. DPA'daki aynı D1 adresli entry1/23 WriteMemType0, display1/18 ReadMemType1 taşıyor; adres eşitliği native metadata aktarım yetkisi değildir. Legacy örneğin ID eksikliği de aynı kaldı. Denetmen yeni komut eşlemesi için kanıt bulunmadığını doğruladı; corpus aktarımı, yanlış aile kabulü veya unknown-button clone ile full hedef kapatılmadı.
