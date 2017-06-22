//var sys = require('sys')
//var exec = require('child_process').exec;
var jsdom = require("jsdom");
const { JSDOM } = jsdom;
var MongoClient = require('mongodb').MongoClient;
var fs = require('fs');
var obj = JSON.parse(fs.readFileSync('credentials.json', 'utf8'));
var url = 'mongodb:\/\/' + obj['user'] + ':' + obj['password'] + '@' +
	obj['host'] + ':' + obj['port'] + '/' + obj['db'];
var counter = 0;
MongoClient.connect(url, function(err, db) {
var main = db.db('data');
  var col = main.collection('records');
  col.find({'RECEPTION NO' : {'$exists' : false}}).each(function(err, mongodb_record) {
      if('header' in mongodb_record) {
          let _id = mongodb_record['_id'];
          let record = fill(mongodb_record);
          col.update({'_id': _id}, {'$set': record});
          counter++;
          if (counter % 100 == 0) {
              console.log('Parsed ' + counter);
              //exec("echo 1 > /proc/sys/vm/drop_caches ; echo 2 > /proc/sys/vm/drop_caches ; echo 3 > /proc/sys/vm/drop_caches ; sync");
          }
      }
   });
});

var $ = require('jquery')(new JSDOM("<html><body><h1>Initializing jquery</h1></body></html>").window);

function fill(mongodb_record)
{
    let record = {};
    let inner = mongodb_record['data']['data'];
    let outer = mongodb_record['header'];
    let dom1 = new JSDOM(inner.replace('\\', ''));
    let dom2 = new JSDOM('<table>' + outer.replace('\\', '') + '</table>');
    ScrapePage(dom2.window.document, record);
    ScrapeRecord(dom1.window.document, record);

    for(let key in record)
    {
      record[key] = $.trim(record[key]);
    }
    return record;
}

function normalize(str, regxp, s1 = '', s2 = '') {
    var matches = str.match(regxp);
    if (matches !== null)
        return str.match(regxp)[0].replace(s1, '').replace(s2, '').trim();
    else
        return '';
};

function ScrapeRecord(doc, record) {
    var fieldset = doc.getElementsByTagName('fieldset')[0];
    var fsText = fieldset.textContent.replace(/(\r\n|\n|\r)/gm, "").trim();
    // Find value between two strings and append it to result
    var fillRecord = function(attr, s1, s2) {
        try {
            var matches = fsText.match('(' + s1 + ')(.*)(' + s2 + ')');
            record[attr] = matches[2].trim();
        } catch (TypeError) {
            record[attr] = '';
        }
    };
    fillRecord('RecordingFee', 'Recording Fee', 'Documentary Fee');
    fillRecord('DocumentaryFee', 'Documentary Fee', 'Total Fee');
    fillRecord('GRANTEE STREET ADDRESS', 'Address1', 'Address2');
    fillRecord('GRANTEE STREET ADDRESS 2', 'Address2', 'City');
    fillRecord('GRANTEE CITY', 'City', 'State');
    fillRecord('GRANTEE STATE', 'State', 'Zip');
    fillRecord('GRANTEE ZIP', 'Zip', 'Mailback Date');
    var notesFieldset = $(doc).find('fieldset:contains("Notes")');
    const regex = /((SE4|SW4|NE4|NW4|NE|NW|SE|SW|N2|S2|W2|E2|N\/2|S\/2|W\/2|E\/2|NE\/4|NW\/4|SE\/4|SW\/4){1,5})($| |,|\n)/g;
    record['SPECIFICATIONS'] = notesFieldset.text().replace("Notes", '');
    record['SEC'] = '';
    record['TWP'] = '';
    record['RNG'] = '';
    record['LEGAL'] = '';
    record['GRANTOR'] = '';
    record['GRANTEE'] = '';

    // Extracting sec twp range and subdiv (LEGAL) from Notes
    var fillFromMatches = function(matches) {
        let str = matches[0];
        record['RNG'] = str.match(/R[0-9]{1,2}/g)[0].replace(',', '');
        record['TWP'] = str.match(/T[0-9]{1,2}/g)[0].replace(',', '');
        record['SEC'] = str.match(/S[0-9]{1,2}/g)[0].replace(',', '');
        let notes = record['SPECIFICATIONS'].replace(str, '').trim();
        let matchesSubdiv = notes.match(regex);
        if(matchesSubdiv !== null) record['LEGAL'] = matchesSubdiv.join(', ');};
        let matches = record['SPECIFICATIONS'].trim().match(/R[0-9]{1,2} T[0-9]{1,2} S[0-9]{1,2}/g);
        if(matches !== null)
        {
            fillFromMatches(matches);
        }
        else{
        matches = record['SPECIFICATIONS'].trim().match(/S[0-9]{1,2} T[0-9]{1,2} R[0-9]{1,2}/g);
        if(matches !== null)
        {
            fillFromMatches(matches);
        }
    }

    var tables = $(doc).find('table[width="100%"]');
    for (var i = 0; i < tables.length; i++) {
        var trHeader = '';
        var rows = $(tables[i]).find('> tbody > tr');
        //SCRAPING LEGAL DATA
        if (i === tables.length - 1) {
            var legalData = tables[i].textContent.replace('Â', ', ');
            let m;
            let matchesSubdiv = legalData.trim().match(regex);
            if(matchesSubdiv !== null)
            {
                record['LEGAL'] += record['LEGAL'] !== '' ? ', ' + matchesSubdiv.join(', ') : matchesSubdiv.join(', ');
            }

            var sec = normalize(legalData, 'Section: .*? ', 'Section: ', '');
            var twp = normalize(legalData, 'Township: .*? ', 'Township: ', '');
            var rng = normalize(legalData, 'Range: .*? ', 'Range: ', '');
            record['Legal data'] = legalData;
            if(sec !== '')
            record['SEC'] += record['SEC'] === '' ? sec : ', '+ sec;
        if(twp !== '')
            record['TWP'] += record['TWP'] === '' ? twp  : ', ' + twp;
        if(rng !== '')
            record['RNG'] += record['RNG'] === '' ? rng : ', ' + rng;
        }

        let grantors = [];
        let grantees = [];

        for (var j = 1; j < rows.length; j++) {
            if (i === 0) {
                var grantor = rows[j].textContent;
                if (grantor !== undefined){
                    grantors.push(grantor.trim());
                }
            }
            if (i === 1) {
                var grantee = rows[j].textContent;
                if (grantee !== undefined){
                    grantees.push(grantee.trim());
                }
            }
        }

        record['GRANTOR'] += $.unique(grantors).join(', ');
        record['GRANTEE'] += $.unique(grantees).join(', ');
    }

    record['SEC'] = record['SEC'].replace('S', '');
    record['TWP'] = record['TWP'].replace('T', '');
    record['RNG'] = record['RNG'].replace('R', '');
}

function ScrapePage(doc, record) {
    let tr = $(doc).find('tr')[0];
    var desc = $(tr).find(' > td').first().text().split('\n');
    record['INSTRUMENT TYPE'] = desc[0];
    record['RECEPTION NO'] = desc[1];
    var text = $(tr).text();

    var normalizeOther = function() {
        record['Legal data'] = '';
        var trs = $(tr).find('table[width="100%"] > tbody > tr');
        for (var i = 0; i < trs.length; i++) {
            var tds = $(trs[i]).find(' > td');
            for (var j = 0; j < tds.length; j++) {
                var regxp = '<b>.*?<\/b>';
                if (tds[j].innerHTML.match(regxp) !== null) {
                    var header = normalize(tds[j].innerHTML, regxp, '<b>', '</b>').replace(':', '').trim();
                    if(header.toLowerCase().indexOf('grantor') === -1 & header.toLowerCase().indexOf('grantee') === -1){
                    var value = tds[j].innerHTML.replace(tds[j].innerHTML.match(regxp)[0], '').replace('\n', ',');
                    record[header] = value;
                    }
                }
            }
        }
    };

    record['name'] = normalize('^.*');
    record['RECORDED DATE']= normalize(text, 'Rec\. Date:.*?Book Page', 'Rec. Date:', 'Book Page');
    let bookPage = normalize(text, 'Book Page:.*Related', 'Book Page:', 'Related');
    let book = normalize(bookPage, 'B:.*P:', 'B:', 'P:');
    let page = normalize(bookPage, 'P:.*$', 'P:');
    record['BOOK']= book;
    record['PAGE']= page;
    record['rel'] = normalize(text, 'Related:.*?Rel Book Page:', 'Related:', 'Rel Book Page:');
    record['relBookPage'] = normalize(text, 'Rel Book Page:.*?Grantor', 'Rel Book Page:', 'Grantor');
    //record.grantor = normalize(text, 'Grantor:.*?Grantee', 'Grantor:', 'Grantee');
    //record.grantee = normalize(text, 'Grantee:.*', 'Grantee:');
    record['numPages'] = normalize(text, 'Num Pages:.*', 'Num Pages:');
    normalizeOther();
}

String.prototype.replaceAll = function(search, replace){
  return this.split(search).join(replace);
}
