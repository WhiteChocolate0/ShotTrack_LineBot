# 衛教圖卡命名規則

這個資料夾用來放「已接種」後要傳送的衛教圖卡。

## 檔名規則

請使用 `vaccines.csv` 的 `Sys_Code` 作為檔名：

```text
{Sys_Code}.png
```

範例：

```text
HBIG-1.png
rHepB-1.png
rHepB-2.png
rHepB-3.png
5in1-1.png
5in1-2.png
13PCV-1.png
MMR-1.png
Var-1.png
JE-1.png
Tdap-IPV.png
```

## 建議格式

- 檔案格式：PNG
- 檔案名稱：只用英文、數字、連字號 `-`
- 尺寸：建議 1040 x 1040 或 1200 x 1200
- 內容：單張圖卡應對應一個疫苗劑次

## 注意

LINE Bot 傳送圖片時需要公開 HTTPS 圖片網址。這個資料夾目前先作為本機圖卡素材庫，之後可以再接上靜態檔案服務或雲端儲存空間。
