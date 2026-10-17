# Ayrı DVP adresleri — statik araştırma

İki salt-okunur inceleme Delta DVP serial sürücüsünde BOOL M0–4095/S0–1023 ve UINT word D0–11999 bölgelerini doğruladı. Üreticinin [Ocak 2016 serial DVP PLC kılavuzu](https://filecenter.deltaww.com/Products/download/06/060302/Manual/DELTA_IA-HMI_Delta-DVP-PLC_CM_EN_20160122.pdf) aynı sınırları verir. Eski farklı TCP/IP/CPU bağlamındaki D9999 sınırı bu kaynağa otomatik uygulanmaz. CPU belleği ve erişim hakkı [DVP programlama kılavuzu](https://filecenter.deltaww.com/Products/download/06/060301/Manual/DELTA_IA-PLC_DVP-PLC_PM_EN_20200605.pdf) ve yetkili proje kataloğunda ayrıca doğrulanır.

PE32 deltaPLC.dll69,632 byte, SHAe14767083390e1d35dbb8d9312d142d83491e75abcf68cd2b42fe807fddd9e72. Controller mapping SHA011b5fa599f45c4ccddb8197e3e384a7358aa6d25f8945d689d289941efde49b. CheckPLCValueRange RVA0x272b bit table0xc250/7 ve word table0xc198/9 kayıt arasında seçim yapar; stride20, min/max inclusive. M bit0xc278, S bit0xc28c ve D word0xc210 bağımsız çözüldü. DLL yüklenmedi veya çalıştırılmadı.

İki gerçek B07S410 kaynakta farklı M/D ve native Link1/MemType0 gözlendi. B03S211 S2 Type1/SubType1 read/write owner bounded partial olarak çözüldü; unknown logo framing nedeniyle donor/roundtrip kabulü değildir. Hash ve nötr gözlemler [JSON araştırmada](DRIVER_ADDRESS_RESEARCH.json); özel proje, logo, tag kataloğu veya DLL dağıtılmaz.

B10S615 driver span SHA06d65fb7b35ef15926bc3f6148b31ac80252a79f23d19304a9e00ad588299a98 private ayarları hash ile sabitler; raw driver kayıtları dışarı verilmez. Link2 etiketi native Link1'e eşitlenmez; DLL device kodları MemType olarak yazılmaz. Core yalnız [tarafsız factual JSON](../profiles/driver_contracts/delta_dvp_serial_2016.json) taşır.

Manual doğrudan isteği HTML döndürdü; downloaded-PDF SHA veya screenshot incelemesi iddia edilmez. Resmi indekslenmiş içerik ve bağımsız statik tablo çözümü kullanılmıştır. Leading-zero-free canonical grammar sistemin kabul alt kümesidir; vendor alternatifleri reddediyor iddiası değildir. UINT zero-decimal dışındaki tipler, diğer driver/bit operand, keypad/PLC ve panel/vendor ayrıca kanıt ister. [Milestone](DRIVER_ADDRESS_MILESTONE.json).
