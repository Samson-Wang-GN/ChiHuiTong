# 原型本地依赖

所有包通过版本固定的 jsDelivr npm 发布路径下载，原型运行时没有 CDN 请求。

| 文件 | 来源 | SHA-256 |
| --- | --- | --- |
| react.min.js | https://cdn.jsdelivr.net/npm/react@18.3.1/umd/react.production.min.js | D949F1C3687AEDADCEDAC85261865F29B17CD273997E7F6B2BFC53B2F9D4C4DD |
| react-dom.min.js | https://cdn.jsdelivr.net/npm/react-dom@18.3.1/umd/react-dom.production.min.js | 35F4F974F4B2BCD44DA73963347F8952E341F83909E4498227D4E26B98F66F0D |
| arco.min.js | https://cdn.jsdelivr.net/npm/@arco-design/web-react@2.66.16/dist/arco.min.js | C5625760318D3A0DF24847017BD28BDD04FE1315C8BBEDB413FD03922A462A08 |
| arco.min.css | https://cdn.jsdelivr.net/npm/@arco-design/web-react@2.66.16/dist/css/arco.min.css | 7084C7BBAEE03DADB995E80A6B7F02FA0C304454C8EBE8184690784B18277EA8 |

Arco 官方源码仓库 https://github.com/arco-design/arco-design ，React 官方源码仓库 https://github.com/facebook/react 。两者均采用 MIT 许可，正文分别保留于 LICENSE-arco、LICENSE-react。禁止直接修改这些上游发布文件；只在共享布局代码中使用组件公开 API。
