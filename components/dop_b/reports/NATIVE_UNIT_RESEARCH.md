# Birim kayıtları ve sahiplik — salt okunur gözlemler

Bu çalışma yalnız native kayıtların framing ve korunmasını inceler. `UnitDirection`, conversion enum değerleri, font ve native piksel yerleşimi kalibre edilmiş sayılmaz. Kurulu vendor dosyaları ve varlıkları repoya kopyalanmadı; IDE çalıştırılmadı.

`UnitTextLenN` doğrudan numeric `Element` sahibinin UTF-16LE, terminal NUL ve CRLF taşıyan uzunluklu kaydıdır. State `wTextLenN` başlıklarından ayrı envanterlenir. Gerçek örneklerde input `Type=6/SubType=1`, display `Type=5/SubType=1` olarak gözlendi. Sıfır uzunluklu frame yalnız okunup korunur; değiştirme yetkisi vermez. Yeni frame/language/font/conversion kayıtları yaratılmaz.

Gözlenen 22 temel alan: `UnitType`, `UnitSrc`, `UnitSrcVar`, `UnitDisplay`, `UnitDisplayVar`, `UnitPercent`, `UnitPercent1Var`, `UnitPercent2Var`, `UnitCustom1Var_1`, `UnitCustom2Var_1`, `BackupUnitSrc`, `BackupUnitDisplay`, `ConvertConstByUnit`, `ShowUnit`, `UnitDirection`, `UnitFontSize0`, `UnitFontName0`, `UnitTextLen0`, `UnitBold`, `UnitItalic`, `UnitUnderline`, `UnitFontColor`. Ek dil alanları da tam ve kanonik sahiplik gerektirir. Bilinmeyen unit ilişkili raw alanlar low-level imzada korunur; public numeric üretimde bilinmeyen alan kabul edilmez.

İki gerçek örnek üzerinde bellekte toplam 30 etkin unit sahibi yeniden sınandı:

| Örnek | Dosya SHA-256 | Model / editör | Sahip |
|---|---|---|---|
| History | `7f35b5fd05537106b46a9791a426a1b3e3a59f8afa1f870595e9c0fd75e24471` | `268505093 / 6.6.0.10` | 21 |
| SC Alarm | `5cc5fa8215be212a3a19d6cd3e78520cddcc355b8e105c7e17b31b7df11e17a9` | `268505088 / 6.6.0.9` | 9 |

Her gerçek no-op bütün sıkıştırılmış kaynak byte'larını korudu. `Olcu / mm` literal değişiminde yalnız bir `UnitTextLen0` raw kaydı değişti; diğer kayıtlar, prefix, thumbnail ve tail eşit kaldı. Saf saved verifier bu adayları okudu; kaynaklar tekrar hash kontrolünde değişmedi. Kaynak veya aday native dosya yazılmadı.

Temsilci bağlar:

- History screen `1`, native element `7`: unit baseline `ba0e7ccde2baa806ff73cc76c54578de763b672ed7bc2b11fa9405b43fa000d7`; tam context `4bc98349f11867c93c9ec658f503ac63005bc9469dec891ddeb35ad27073062d`; aday `dbd5f938cd4c6dfa5dd582eeb5f9467c0c9a2f6cf5d66736c8b54a1f41b04bfa`. Tek değişiklik section 53 / record 111.
- SC Alarm screen `8`, native element `43`: unit baseline `b1f7783c5c3993f7647c29047b0dce0ec70c86e3b3cd26d1ebbe1d210b50858f`; context `c65eb9b5bc6dc9d82b4f334bd40f41309424d86d70523ba51b6a8f7fa19ad061`; aday `cc43837e527ed388323ba2ce4ef1314983f491c1b8e7a9fd427eda7bb6d1b8e7`. Tek değişiklik section 145 / record 57.

Bu model/editörler seçilmiş `DOP-110IS/DIAScreen` ve `DOP-B07S411/DOPSoft 2` profillerinin kabulü değildir. Gözlemden bütün aileye destek çıkarılmaz. Installed holdout bağları özel dosya yoluna runtime bağımlılık getirmez.

Public tasarım farklı bir sözleşme kullanır: numeric `unit_label`, aynı sayfada konumu ve görünümü açık ayrı bir text nesnesine bağlanır. Embedded unit bütün dillerde kapalı ve gerçek boş NUL frame olmalıdır; birim dönüşümünün identity olduğunu söyleyen kaynak-local qualified raw baseline ayrıca gerekir. `ShowUnit=0` tek başına conversion kabulü değildir. External unit operands kapalıdır. Numeric değer dönüşümü değişmeden unit context imzası orijinal sahibiyle eşit kalır; unit geometrisi text sahibinde üretilir.

Kavramsal browser ölçümü native font/piksel kanıtı değildir. Tam üretim, iki gerçek profil, vendor açma/kaydetme/derleme/simülasyon ve panel kabulü açık kalır. [Güncel milestone](NATIVE_UNIT_MILESTONE.json), [bağımsız denetim](NATIVE_UNIT_REVIEW.md).
