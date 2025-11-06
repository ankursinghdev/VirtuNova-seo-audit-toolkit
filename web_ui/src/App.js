import React from 'react';
import report from '../report.json';
export default function App(){ return (<div style={{padding:20}}><h1>VirtuNova — SEO Audit</h1><pre>{JSON.stringify(report,null,2)}</pre></div>); }
