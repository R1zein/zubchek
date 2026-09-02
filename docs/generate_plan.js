const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  WidthType, AlignmentType, VerticalAlign, HeadingLevel, BorderStyle,
} = require('docx');

const FONT = 'Times New Roman';
const SZ = 28;      // 14pt
const SZT = 24;     // 12pt в таблице

const p = (opts) => new Paragraph(opts);
const t = (text, o = {}) => new TextRun({ text, font: FONT, size: o.size || SZ, bold: !!o.bold, ...o });

const line = (text, o = {}) =>
  p({
    alignment: o.alignment || AlignmentType.LEFT,
    spacing: { line: o.line || 276, after: o.after === undefined ? 0 : o.after },
    indent: o.indent,
    children: [t(text, { bold: o.bold, size: o.size })],
  });

// ---------- Шапка: номер слева, УТВЕРЖДАЮ справа ----------
const headerTable = new Table({
  columnWidths: [4400, 4955],
  width: { size: 9355, type: WidthType.DXA },
  borders: {
    top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
    left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
    insideHorizontal: { style: BorderStyle.NONE }, insideVertical: { style: BorderStyle.NONE },
  },
  rows: [
    new TableRow({
      children: [
        new TableCell({
          width: { size: 4400, type: WidthType.DXA },
          margins: { top: 0, bottom: 0, left: 0, right: 100 },
          children: [line('№ ____________________', { bold: true })],
        }),
        new TableCell({
          width: { size: 4955, type: WidthType.DXA },
          margins: { top: 0, bottom: 0, left: 100, right: 0 },
          children: [
            line('УТВЕРЖДАЮ', { bold: true, after: 240 }),
            line('Президент АО «Медицина»', { bold: true, after: 240 }),
            line('Г.Е. Ройтберг', { bold: true, after: 240 }),
            line('«____» ____________ 2026 г.', { bold: true }),
          ],
        }),
      ],
    }),
  ],
});

// ---------- Таблица мероприятий ----------
const COLS = [700, 3500, 1500, 1900, 1755]; // = 9355

const cellPara = (text, o = {}) =>
  p({
    alignment: o.alignment || AlignmentType.LEFT,
    spacing: { line: 240, after: 0 },
    children: [t(text, { size: SZT, bold: o.bold })],
  });

const cell = (paras, width, o = {}) =>
  new TableCell({
    width: { size: width, type: WidthType.DXA },
    verticalAlign: VerticalAlign.CENTER,
    margins: { top: 60, bottom: 60, left: 80, right: 80 },
    children: paras,
  });

const headRow = new TableRow({
  tableHeader: true,
  children: [
    ['№\nп/п', COLS[0]],
    ['Наименование мероприятия', COLS[1]],
    ['Срок\nисполнения', COLS[2]],
    ['Ответственный', COLS[3]],
    ['Контролер', COLS[4]],
  ].map(([txt, w]) =>
    cell(txt.split('\n').map((s) => cellPara(s, { alignment: AlignmentType.CENTER, bold: true })), w)
  ),
});

// [мероприятие, срок(и), ответственный, контролер]
const ITEMS = [
  ['Утвердить функциональные требования и границы пилотного внедрения сервиса «Zubchek» — цифровой оценки гигиены полости рта по фотографии (далее — ЦОГ): перечень подразделений, категории пациентов, состав отчета для врача',
    ['07.09.2026'], 'Руководитель проекта', 'Заведующий стационаром'],

  ['Развернуть продуктивную инфраструктуру сервиса (сервер приложения, база данных, подключение ИИ-провайдера), настроить домены и SSL-сертификаты',
    ['18.09.2026'], 'Служба ИТ', 'Руководитель проекта'],

  ['Провести оценку соответствия обработки персональных данных и медицинских фотоизображений требованиям Федерального закона № 152-ФЗ, подготовить и утвердить форму информированного согласия пациента',
    ['25.09.2026'], 'Юридическая служба', 'Руководитель проекта'],

  ['Провести функциональное и нагрузочное тестирование сервиса, устранить выявленные замечания, обеспечить резервное копирование данных',
    ['02.10.2026'], 'Служба ИТ', 'Руководитель проекта'],

  ['Направить в финансово-экономическую службу данные для определения возможности оказания услуги ЦОГ в ОМС/ДМС, а также для расчета стоимости услуги',
    ['09.10.2026'], 'Руководитель проекта', 'Финансово-экономическая служба'],

  ['Дать заключение о возможности оказания услуги ЦОГ в ОМС/ДМС',
    ['16.10.2026'], 'Финансово-экономическая служба', 'Руководитель проекта'],

  ['Внести услугу ЦОГ в прейскурант клиники',
    ['23.10.2026'], 'Финансово-экономическая служба', 'Руководитель проекта'],

  ['Разработать и утвердить регламент работы врача с сервисом: маршрут пациента, порядок фотопротокола, интерпретация индексов гигиены, оформление результата в медицинской информационной системе',
    ['23.10.2026'], 'Заведующий отделением стоматологии', 'Руководитель проекта'],

  ['Провести обучение врачей-стоматологов и медицинских сестер работе с сервисом ЦОГ',
    ['30.10.2026'], 'Руководитель проекта', 'Заведующий отделением стоматологии'],

  ['Провести пилотную эксплуатацию сервиса (не менее 30 пациентов), собрать обратную связь врачей и пациентов, устранить замечания',
    ['27.11.2026'], 'Заведующий отделением стоматологии', 'Руководитель проекта'],

  ['Направить в службу маркетинга формы для создания страницы на сайте',
    ['30.10.2026'], 'Руководитель проекта', 'Служба маркетинга'],

  ['Сделать на сайте страницу с информированием о возможности прохождения ЦОГ в клинике',
    ['20.11.2026'], 'Служба маркетинга', 'Руководитель проекта'],

  ['Направить в отдел продвижения услуг презентацию о возможности прохождения ЦОГ в клинике',
    ['06.11.2026'], 'Руководитель проекта', 'Отдел продвижения услуг'],

  ['Направить в службу клиентского сервиса презентацию о возможности прохождения ЦОГ в клинике',
    ['06.11.2026'], 'Руководитель проекта', 'Служба клиентского сервиса'],

  ['Подготовить скрипт о возможности прохождения ЦОГ в клинике',
    ['13.11.2026'], 'Служба клиентского сервиса', 'Руководитель проекта'],

  ['Проводить мониторирование количества проведенных исследований ЦОГ, доли успешных анализов фотографий и обращений в службу поддержки',
    ['10.11.2026', '10.12.2026', '15.01.2027'], 'Руководитель проекта', 'Заведующий стационаром'],

  ['Отчет о выполнении плана',
    ['22.01.2027'], 'Руководитель проекта', 'Президент АО «Медицина»'],
];

const rows = [headRow].concat(
  ITEMS.map((it, i) =>
    new TableRow({
      children: [
        cell([cellPara(String(i + 1) + '.', { alignment: AlignmentType.CENTER })], COLS[0]),
        cell([cellPara(it[0], { alignment: AlignmentType.LEFT })], COLS[1]),
        cell(it[1].map((d) => cellPara(d, { alignment: AlignmentType.CENTER })), COLS[2]),
        cell([cellPara(it[2], { alignment: AlignmentType.CENTER })], COLS[3]),
        cell([cellPara(it[3], { alignment: AlignmentType.CENTER })], COLS[4]),
      ],
    })
  )
);

const table = new Table({
  columnWidths: COLS,
  width: { size: 9355, type: WidthType.DXA },
  rows,
});

// ---------- Подпись ----------
const signTable = new Table({
  columnWidths: [5355, 4000],
  width: { size: 9355, type: WidthType.DXA },
  borders: {
    top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE },
    left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
    insideHorizontal: { style: BorderStyle.NONE }, insideVertical: { style: BorderStyle.NONE },
  },
  rows: [
    new TableRow({
      children: [
        new TableCell({
          width: { size: 5355, type: WidthType.DXA },
          margins: { top: 0, bottom: 0, left: 0, right: 100 },
          children: [line('Руководитель проекта')],
        }),
        new TableCell({
          width: { size: 4000, type: WidthType.DXA },
          margins: { top: 0, bottom: 0, left: 100, right: 0 },
          children: [line('_________________ / ______________', { alignment: AlignmentType.RIGHT })],
        }),
      ],
    }),
  ],
});

const doc = new Document({
  styles: {
    default: {
      document: { run: { font: FONT, size: SZ } },
    },
  },
  sections: [
    {
      properties: {
        page: {
          margin: { top: 1134, right: 850, bottom: 1134, left: 1701 },
        },
      },
      children: [
        headerTable,
        p({ spacing: { after: 240 }, children: [t('')] }),
        line('ПЛАН', { alignment: AlignmentType.CENTER, bold: true }),
        line('внедрения проекта «Zubchek» — цифровой оценки гигиены полости рта по фотографии', { alignment: AlignmentType.CENTER, bold: true, after: 240 }),
        p({
          alignment: AlignmentType.BOTH,
          spacing: { line: 276, after: 0 },
          indent: { firstLine: 709 },
          children: [
            t('Цель: ', { bold: true }),
            t('ввод сервиса ЦОГ в промышленную эксплуатацию и выполнение не менее 100 исследований гигиены полости рта к моменту окончания плана.'),
          ],
        }),
        p({
          alignment: AlignmentType.BOTH,
          spacing: { line: 276, after: 0 },
          indent: { firstLine: 709 },
          children: [t('Координатор: ', { bold: true }), t('Руководитель проекта ______________________.')],
        }),
        p({
          alignment: AlignmentType.BOTH,
          spacing: { line: 276, after: 240 },
          indent: { firstLine: 709 },
          children: [t('Бюджет: ', { bold: true }), t('в пределах утвержденного бюджета службы ИТ (инфраструктура и оплата ИИ-провайдера).')],
        }),
        table,
        p({ spacing: { after: 360 }, children: [t('')] }),
        signTable,
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(process.argv[2] || 'plan.docx', buf);
  console.log('written');
});
