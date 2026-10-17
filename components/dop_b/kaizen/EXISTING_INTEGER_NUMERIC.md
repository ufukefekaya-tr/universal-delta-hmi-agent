# Mevcut sayısal gösterim ve giriş sınırı

Gözlem: aynı görünen sayı nesnesi; storage, gösterim, giriş ve compiler limit dönüşümünde farklı kurallara sahiptir. Gösterimdeki doğru decimal ayırma, fractional keypad sınırının güvenli yazıldığını kanıtlamaz.

Kök neden: kaynak MemFmt/MemLen değiştirmeden ayar yapmak ile UINT donor'u signed clone'a çevirmek aynı yetki gibi ele alınırsa tip/ölçek değişimi gizlenir. Ayrıca binary-float limit hattı, ham integer gösterim hattından farklıdır.

Karşı görüş: mevcut kaynakta signedF1 örneğinin bulunması bütün F ve keypad kombinasyonlarını açmalı. Buna karşılık primary renderer/compiler izi yalnız belirli gösterim adımlarını destekler; vendor kaydı, glyph, CRT/thread/locale ve gerçek runtime kabulü halen ayrıdır. Matematiksel endpoint uygunluğu tek başına keypad yetkisi değildir.

Minimum değişiklik: ayrı source-pinned descriptor/opcode ile yalnız IntNum/DotNum ve kaynakF0 input integral limits. Mevcut WORD storage ve adresler immutable. Fractional input ve dynamic/conditional özellikler fail closed. Aynı owner appearance işlemi disjoint orijinal scalar alanlarda birleşir.

Test: neutral INT/UINT source fixture, full raw-range/digit sınırları, malformed ve stale pins, sourceF1input→F0 reddi, no-op eşdeğer limit spelling, complete BODY expectation/restoration/reopen/replay, authority drift/atomic save ve dokuz-tool stdio. Üretici helper'ının output'u bağımsız expected-body oracle yerine kullanılmaz.

Rollback: kaynak korunur; yalnız yeni candidate kaydedilir. No-op kaynak dosyanın tamamına eşit olmalıdır. Eski existing_edit yolu ve stock profiller genişletilmez.

Genellenebilirlik sınırı: bu sözleşme yalnız exact B10 model/version/closed graph stored settings'tir. Başka model, floating/64bit/TIME, F>0 input, driver/binding değişimi, native pixel/vendor/runtime/panel veya safety interlock kabulü açmaz.
