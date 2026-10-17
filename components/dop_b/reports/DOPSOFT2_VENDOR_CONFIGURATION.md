# Gerçek B referansı ve MCP adayı

Kullanıcının yeni tarafsız blank DPS kaynağı, dar vendor örnek oluşturma/kaydetme yetkisiyle örneklendi. Model **DOP-B10S615**,1024×600, raw kimlik−1341103792/uint2953863504. Dört ayrı Set/Reset/Push/Kalıcı ve Word/Unsigned Decimal input/display owner'ı, modal property görüntüleriyle eşlendi. Native kaynak ve görüntüler proje-local ignored alanda tutuluyor; genel repo bunları dağıtmıyor. [Hash/kimlik/owner/image kaydı](DOPSOFT2_VENDOR_CONFIGURATION.json).

Kurulum klasörü etiketi `DOPSoft 2.00.07`; actual executable FileVersion/ProductVersion `4, 0, 7, 4`, Build Date2015/03/13, SHA `9ed92401cd08e2be8bfc2df3a40dee4e99e9f605da7a4fa9605f9e2754821eeb`. Native serialized Version `4.00.07.04`. Bunlar ayrı gözlemlerdir; pazarlanan sürüm independently confirmed değildir. Klasör etiketinden veya PE version'dan DOPSoft4 dönüşüm davranışı ya da bütün B uyumluluğu çıkarılmaz. Kaydedilmiş gerçek B DPS format/model kimliği doğrudan doğrulandı.

Source55044byte/SHA `c7830ddfc6305f479b21e441107eccf5441b3273ba62c73fac278d4c7f3d3052`. Dokuz gerçek SDK MCP çağrısından çıkan candidate55268byte/SHA `d96dacf3b05dea694a82915e25dda0e3880d6b2747e347776172915f9e6cc57b`. Candidate altı original+altı append owner içerir. Orijinal globals/owners/page/Aux/thumbnail/tail ve ilk37prefix değişmedi; gövde uzunluğu43736→52011, declaration52011 oldu.

Set donor Write=M0; input Write=D0; display Read=D0. Üç diğer button source'un Read/Write alanı None. Source ReadLink/WriteLink1 ve MemType0, adres içindeki Link2 ile karıştırılmadan korunuyor. Input donor native limits0..9999 taşıyor; display native MinValue/MaxValue taşımıyor. İki durum caption'ları ve safe renkler eklenen managed kontrolün IR'ından geliyor.

**Aday dosya offline qualification içindir; panele yüklemeye hazır program değildir.** Unbound original referans nesneleri korunmuş. Vendor compile/simulation/driver/runtime/native pixels/panel testi yapılmadı. Clean program, arbitrary address namespace, new page/navigation/macro/alarm ve DOP-100 gerçek profil açık. [İnceleme](CONTROL_GENERATION_REVIEW.md), [kullanım](../docs/CONTROL_GENERATION.md).
