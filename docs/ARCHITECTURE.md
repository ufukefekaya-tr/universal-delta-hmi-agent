# Aile izolasyonu

Ortak katman native byte veya vendor enum dÃ¼zenlemez. MCP Ã§aÄŸrÄ±sÄ±nÄ± aÃ§Ä±k aile Ã¶nekiyle ayrÄ± kurulu backend'e gÃ¶nderir. DOP-B modÃ¼lÃ¼ `universal_hmi.cli`, DIAScreen hedef sÃ¶zleÅŸmesi `universal_diascreen_hmi.cli`dir. Aile profili ve dosya uzantÄ±sÄ± Ã¶n kontroldÃ¼r; gerÃ§ek native iÃ§erik, model ve sÃ¼rÃ¼m denetimini backend yapar.

Her aile iÃ§in dÃ¶rt ayrÄ±k kÃ¶k gerekir: immutable kurulum, workspace, profile registry, state. Bunlar birbirinin altÄ± olamaz. Ä°ki ailenin kÃ¶kleri de Ã§akÄ±ÅŸamaz. Symlink/junction reddedilir. Python Ã§alÄ±ÅŸtÄ±rÄ±labilir dosyasÄ±, venv ve temel Python Ã§alÄ±ÅŸma ortamÄ±nÄ±n tamamÄ± (bytecode, import hook ve baÄŸÄ±mlÄ±lÄ±klar dahil) ile profil aÄŸacÄ± hash ile sabitlenir; Ã§aÄŸrÄ± Ã¶ncesi/sonrasÄ± yeniden doÄŸrulanÄ±r. YapÄ±landÄ±rma ve pin dosyalarÄ± mutable workspace/state dÄ±ÅŸÄ±nda kalÄ±r.

Bu ayrÄ±m aynÄ± OS kullanÄ±cÄ±sÄ±yla Ã§alÄ±ÅŸan sÃ¼reÃ§lerde hata/kapsam izolasyonudur, kÃ¶tÃ¼ niyetli backend'e karÅŸÄ± OS sandbox deÄŸildir. GÃ¼venilmeyen yÃ¼rÃ¼tÃ¼lebilir kod kaydedilmez. BaÄŸÄ±mlÄ±lÄ±klar kurulumda kilitle doÄŸrulanÄ±r; yerel Python import kÃ¶klerindeki tÃ¼m dosyalar her Ã§aÄŸrÄ±da yeniden doÄŸrulanÄ±r. Ä°ÅŸletim sisteminin dÄ±ÅŸ DLL dosyalarÄ± bu envantere dahil deÄŸildir; bu kontrol bir OS sandbox veya bÃ¼tÃ¼n sistem doÄŸrulamasÄ± deÄŸildir.

Oturum ve plan kimlikleri gateway'in aile + backend sÃ¼reÃ§ nesli + kimlik tÃ¼rÃ¼ tablosundan rastgele dÄ±ÅŸ kimliÄŸe Ã§evrilir. DiÄŸer aileye, farklÄ± tÃ¼r alanÄ±na veya yeniden baÅŸlatÄ±lmÄ±ÅŸ oturuma ait kimlik reddedilir. YalnÄ±z protokolÃ¼n Ã¼st seviye kimlik alanlarÄ± Ã§evrilir; tag adresleri ve tasarÄ±m metinleri deÄŸiÅŸtirilmez. PlanÄ±n oturuma ait olup olmadÄ±ÄŸÄ±nÄ± native backend ayrÄ±ca kontrol eder.

SÃ¼reÃ§ arÄ±zasÄ± diÄŸer aileyi kapatmaz. Native kaynak ve candidate yetkisi backend'e aittir. Gateway timed-out mutasyon sonucunu baÅŸarÄ±ya Ã§eviremez: kullanÄ±cÄ± yeni oturumda Ã§Ä±ktÄ±/diff'i incelemelidir; mevcut dosya Ã¼zerine yazÄ±lmaz. RAM oturumlarÄ± kalÄ±cÄ± iÅŸ kuyruÄŸu deÄŸildir. DOP-B kalÄ±cÄ± job runner'Ä± ayrÄ± sÃ¼rÃ¼mde korunur.

## TaÅŸÄ±ma

Repo ve daÄŸÄ±tÄ±m dosyalarÄ±nda eski host yolu bulunmaz. `.local/gateway.json` yollarÄ± bulunduÄŸu klasÃ¶re gÃ¶redir; bu dosya yerel kurulum sÄ±rasÄ±nda oluÅŸur. Sanal ortamlar baÅŸka bilgisayara kopyalanmaz; temiz paketteki kurulum tekrar Ã§alÄ±ÅŸtÄ±rÄ±lÄ±r. Profil/driver/source yetkileri Ã¶zel proje girdisi olarak ayrÄ±ca taÅŸÄ±nÄ±r; mÃ¼ÅŸteri native dosyasÄ± genel daÄŸÄ±tÄ±ma eklenmez.

## BaÄŸÄ±mlÄ±lÄ±k sÄ±nÄ±rlarÄ±

DOP-B'nin pinli Ã¶zgÃ¼n kaynak sÃ¼rÃ¼mÃ¼ ayrÄ± arÅŸiv olarak daÄŸÄ±tÄ±lÄ±r; iÃ§eriÄŸi DIAScreen paketine kopyalanmaz. Tarihsel upstream DIAScreen kodunun lisansÄ± belirtilmediÄŸi iÃ§in yeni daÄŸÄ±tÄ±mda yoktur. BaÄŸÄ±msÄ±z DIAScreen ajanÄ± aynÄ± davranÄ±ÅŸlarÄ± Ã¶zgÃ¼n olarak geliÅŸtirir. Tarihsel kaynak envanteri, yeni uygulamanÄ±n tamamlandÄ±ÄŸÄ±na dair kanÄ±t deÄŸildir.

## DoÄŸrulama maliyeti

Her Ã§aÄŸrÄ± Ã¶ncesi/sonrasÄ± tÃ¼m Python import kÃ¶kleri yeniden okunur. Bu Windows kurulumunda 6.619 dosyalÄ± envanter iÃ§in tek doÄŸrulama yaklaÅŸÄ±k 13 saniye Ã¶lÃ§Ã¼ldÃ¼; disk ve gÃ¼venlik yazÄ±lÄ±mÄ±na gÃ¶re deÄŸiÅŸir. Ã‡aÄŸrÄ± gecikmesi bu maliyeti iÃ§erir. DoÄŸrulama atlanarak veya yalnÄ±z dosya zamanÄ±na gÃ¼venilerek hÄ±zlandÄ±rÄ±lmaz.

## DIAScreen implicit session integration

The original DIAScreen backend has one implicit project per process. The gateway creates a new backend handle for every successful open and requires an opaque `session_id` on all project tools. It never reuses one project's implicit state for another. `close_session` closes its process; eight open sessions are allowed per gateway. Backend failures invalidate only that session. Profile objects are read from the host registry, never accepted as an alternative inline tool override.

All30 audited DIAScreen tool names and their dynamic schemas are retained. Editing aliases create plans and do not grant application authority. Proposal preview/validation use an exact plan digest; current preview remains explicitly separate. Family routes preserve source/profile/plan consent requirements rather than trying to normalize different native contracts into one guessed schema.
