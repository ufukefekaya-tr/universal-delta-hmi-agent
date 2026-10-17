# Makro ve global Alarm — bağımsız teknik denetim

**Kapsam sonucu: OFFLINE_PASS.** Denetmen `/root/emitter_counterreview` salt okunur çalıştı. Gerçek hedef profilleri, vendor derlemesi, panel, native alarm görünümü ve tam V1 bu sonuca dahil değildir. [Hash ve senaryo kaydı](NATIVE_MACRO_ALARM_MILESTONE.json).

Denetmen 225 benzersiz testi, 0 failure/error/skip ile 25.706 saniyede çalıştırdı. Bu koşunun revision'ı `d5499f88054a757a3939995bcc51233898521faba5682c9b9767e315c6135c54` idi. Ardından yalnız taşıma raporunun yol temizleyicisi değişti; denetmen bu farkı ayrıca Windows yolu, kaçış, URI, yüzde kodlaması, harf büyüklüğü ve en uzun eşleşme senaryolarıyla doğruladı. Root son 40 kaynak hash'inin tamamını içeren `c25e69fe9a6401e4d24a0b036345b5978d7478eb90581320f1b3652689d41931` revision'ında 225 testi tekrar geçti. Aynı byte'lar için birbirinden ayrı bu kanıtlar birleştirildi; ilk koşu son script revision'ında çalıştırılmış gibi sunulmadı.

## Karşı örnekler ve kapanış

| Bulgu | Tetikleyici ve etki | Düzeltme | Bağımsız tekrar kontrolü |
|---|---|---|---|
| M1 — önemli | Aynı semantik makro, boş satırı/yerleşimi/native uzunluk yazımını kaybediyordu | Semantik no-op bütün orijinal record byte'larını döndürür; doğrulayıcı tam eşitlik ister | PASS: tab/space, boş satır, sıfır dolgulu uzunluk; loss `MACRO_NOOP_CHANGED` |
| A1 — önemli | Bilinmeyen ASCII Picture size/scalar, suffix'i yanlış biçimde tam saydırabiliyordu | Yalnız gözlenmiş scalar/frame sözleşmeleri global sınır kanıtıdır; bilinmeyen bölüm salt okunur | PASS: fake header, duplicate Alarm, opaque picture, eksik END ve bilinmeyen scalar |
| A2 — önemli | Minimum değişirken korunmuş maksimumun genişliği veya paired storage çelişkisi kaçabiliyordu | İki final limit de ortak tip/storage/pair sözleşmesiyle sınanır | PASS: retained unsigned overflow, negatif, IEEE underflow ve çelişkili çift |

Denetmen ayrıca immutable donor sırasını, çift native owner eşlemesini, orphan/repeated ELSE/ENDIF'i, yanlış width/operand metadata'sını, kaynak değişikliğini, çoklu owner işlem sırasını ve duplicate global Alarm işlem reddini sınadı. İki container için birleşik makro/property/iki-alarm-index işlemi aynı sonucu verdi; kaynak, diğer kayıtlar, prefix ve thumbnail korundu.

Public servis karşı örneklerinde onaylanan Clock makrosu çalışırken eklenmiş unmanaged Background makrosu ve değişmiş Clock zamanlaması reddedildi. Read-only tag'a yazma reddedildi; public Alarm gate'i kaynak kuyruğundaki izinsiz değişiklikle aşılamadı. Bu kontroller üretilen dosyanın yeniden okunan sözleşmesine bağlıdır.

## Gerçek dosya spot kontrolleri

Bağımsız denetmen resmi Alarm EN, History ve FullDemo örneklerinde tam dosya/kuyruk no-op eşitliğini ve suffix sınırlarını doğruladı. İki dolu örnekte yalnız tek mesaj değiştirilip kalan kayıtlar korundu; History'de mesaj kaydı olmadığı için mutasyon NOT_APPLICABLE olarak ayrıldı. FullDemo'daki üç tam programda semantic no-op ve verifier geçti; öncesindeki yedi desteklenmeyen program açık hata verdi.

Diğer uygulayıcıdan ayrı kaynak okuyucu güncel makro modülünde iki tam program değişikliğini ve üç gerçek kaynakta kontrollü Alarm alanı değişikliğini doğruladı. Önceki 35 makro taraması byte-noop düzeltmesinden önceki tarihsel gözlemdir. 23 kaynak toplu resource gözlemi için tam manifest saklanmadığından 23 ayrı artifact-bound qualification iddiası yapılmaz. Kaynak dosyalar ve vendor varlıkları repoya alınmadı.

## Açık kabul sınırları

Public macro IR; internal UINT/UDINT/DINT atama, BOOL bit ve UINT eşitlik koşulu ile sınırlı, source-local kalibre profile/line/owner/trigger/schedule sözleşmesi gerektirir. Varsayılan registry makro donor'u sağlamaz. Low-level toplama ayrı yetenektir. External/DIA Tag/alias, REAL/TIME ve diğer koşullar açık hata verir.

Alarm tarafında yalnız mevcut, kaynak sözleşmesi doğrulanmış global record alanları değiştirilebilir. Public Alarm IR, BOOL trigger bit eşlemesi, aktif şerit/tablo/tarihli geçmiş ve native view bağımlılıkları açık kalır. Gerçek production `PRODUCTION_EMISSION_PENDING` ile kapalıdır. Önemli teknik bulgu kalmadı; eksik özellikler kabul edilmiş sayılmadı. Son kaynağın temiz taşıma kabulü ayrıca taşıma raporuna (tarihsel yerel kanıt; genel pakete dahil değil: `history/225/relocation_verification.json`) bağlanır.

## Güncel temiz taşıma kapanışı

Kaynak commit `55ef69390bb51fabfba5f1603e9b8477488a47b1`, bağımsız Git clone ve yeni venv ile **225/225**, skipsiz, aynı `c25e69…` revision'ında geçti. Denetmen gerçek checkout'un HEAD/.git/origin/alternates durumunu, system-site kapalı ortamı, eski PATH/PYTHONPATH/PYTHONHOME olmadan unrelated cwd'den yeni source import'unu, editable direct URL'yi, 30 lock pin'ini ve pip check'i ayrı doğruladı. 40 dosya hash'i ve 225 benzersiz test ID'si iki ağaçta birebir eşleşir. Kaydedilen taşıma raporu ve test logu gerçek yeni ortamdaki çıktı ile eşittir; yayımlanan kurulum logu genel host placeholder'ları içerir. Önemli taşıma bulgusu yoktur.

Bu kontrol aynı Windows host'unda ayrı konum/ortam testidir; ikinci fiziksel PC veya Linux/macOS çalışması gibi sunulmaz. Runtime vendor kurulumu ve eski checkout olmadan çalıştı; vendor/physical kabul hâlâ NOT_RUN. Son rapor/belge commit'i executable kaynakları değiştirmez. Kanıt (tarihsel yerel kanıt; genel pakete dahil değil: `history/225/relocation_verification.json`).
