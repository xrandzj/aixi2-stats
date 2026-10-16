# 《艾希：续》众筹自动统计

每小时自动抓取摩点众筹数据，归档到 `records.tsv`，并生成手机可看的 `index.html`。

## 一键部署（约 5 分钟）

### 第 1 步：创建 GitHub 仓库

1. 打开 <https://github.com/new>
2. 仓库名填 `aixi2-stats`（或任意喜欢的名字）
3. **选 Public**（免费 GitHub Pages 只支持公开仓库）
4. 其它保持默认，点 **Create repository**

### 第 2 步：上传本目录的文件

把以下文件全部上传到仓库**根目录**（注意 `.github` 是文件夹，要保留结构）：

```
scrape.py
records.tsv
index.html
README.md
.gitignore
.github/workflows/scrape.yml
```

**最简单的上传方式**（网页操作，不用装 git）：

1. 在刚创建的仓库页面，点 **Add file → Upload files**
2. 把上面这些文件和文件夹**拖进去**
3. 提交信息随便写，点 **Commit changes**

> 上传 `.github/workflows/scrape.yml` 时，网页会帮你创建 `.github` 文件夹，保持这个结构即可。

### 第 3 步：开启 GitHub Pages（手机访问用）

1. 仓库页面点 **Settings → Pages**
2. **Source** 选 **Deploy from a branch**
3. **Branch** 选 `main`，文件夹选 `/ (root)`，点 **Save**
4. 等 1 分钟左右，页面顶部会出现网址：

```
https://你的用户名.github.io/aixi2-stats/
```

这个网址就是手机要收藏的地址。

### 第 4 步：验证自动任务

1. 仓库页面点 **Actions** 标签
2. 左侧会看到 `scrape` 工作流
3. 点右侧 **Run workflow → Run workflow**（手动触发第一次，立即验证）
4. 等它跑完变绿 ✓，说明成功

之后它会**每小时自动跑一次**，你什么都不用管。

## 手机怎么看

浏览器打开第 3 步那个网址（`https://你的用户名.github.io/aixi2-stats/`），
点浏览器菜单「添加到主屏幕」，之后就像 App 一样点开即看。

## 文件说明

| 文件 | 作用 |
|---|---|
| `scrape.py` | 抓取 + 算增量 + 归档 + 生成网页 |
| `records.tsv` | 数据源（Tab 分隔，每行一条统计） |
| `index.html` | 手机看的网页表格（自动重建） |
| `.github/workflows/scrape.yml` | 每小时定时任务 |

## 常见问题

**Q：Actions 跑失败了怎么办？**
点开失败的 run，看 `Run scraper` 步骤的报错。最常见是摩点页面反爬导致解析失败——
把报错截图发我即可，我来修抓取逻辑。

**Q：数据会公开吗？**
会。GitHub Pages 是公开网页。不过这里统计的本来就是摩点公开的众筹数据，
不涉及你的个人信息。如果介意公开，可以不开 Pages，只在仓库里看 `records.tsv`。

**Q：能改成别的频率吗？**
能。改 `.github/workflows/scrape.yml` 里的 `cron` 表达式即可。
（`0 * * * *` = 每小时整点，UTC 时间）
