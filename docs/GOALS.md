# Goals

| Goal | Sahip | Kabul | Durum |
|---|---|---|---|
| U0 Kaynak ve kayıp envanteri | Çatı ajanı | İki sohbet + N002–N016 + upstream işlevlerinin açık kaydı | Envanter hazır; son aktarım denetimi bekliyor |
| U1 İzole ortak MCP | Çatı ajanı | Ayrı süreç/kökler, profil/hash/kimlik kontrolleri, gerçek stdio | Uygulandı; 41 test ve bağımsız teknik ara inceleme geçti |
| U2 DOP-B bağlantısı | Çatı ajanı | Pinli0.2.0 ayrı kurulum, dokuz dosya aracı, kaynak korunumu | Windows offline testleri geçti; headless queue ortak API'ye henüz bağlanmadı |
| U3 Bağımsız DIAScreen repo/MCP | DIAScreen ajanı | Proje agnostik kaynak, tam özellik eşleştirmesi ve testler | Aktif bağımsız görev; teslim bekliyor |
| U4 İki backend entegrasyonu | Çatı ajanı | Her iki gerçek paketin şeması, ek araçları, aile negatifleri | U3 teslimine bağlı açık |
| U5 Eksiksizlik ve taşınabilir teslim | Bağımsız denetmen + çatı | Hiçbir eşleştirilmemiş özellik yok; temiz kurulum/taşıma ve final manifest | Windows temiz kurulum geçti; iki aile final teslimi açık |
| U6 Vendor ve fiziksel kabul | İnsan | Exact model/dosya/çalışma kanıtı | Bu offline işte yapılmıyor |

U0–U2 ara kabulü, U3–U5 tamamlanmış demek değildir. Ortak çatı tüm Delta modellerini veya ailelerin bütün özelliklerini doğruladığı iddiasında bulunmaz.
