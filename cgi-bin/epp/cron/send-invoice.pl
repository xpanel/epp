#!/usr/bin/perl

###############################################################################
#
#	-------------------------
#			XPanel EPP Server
#		-------------------------
#
#	Version: 1.0.0
#	Web Site: http://www.xpanel.com/
#
#	(c) Copyright 2017 XPanel Ltd.
#
# *  XPanel Ltd. licenses this file to You under the Apache License, Version 2.0
# *  (the "License"); you may not use this file except in compliance with
# *  the License.  You may obtain a copy of the License at
# *
# *      http://www.apache.org/licenses/LICENSE-2.0
# *
# *  Unless required by applicable law or agreed to in writing, software
# *  distributed under the License is distributed on an "AS IS" BASIS,
# *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#
###############################################################################



use lib '/var/www/cgi-bin/epp/lib';
use strict;
use warnings;
use MIME::Lite;
use HTML::Template;
use EPP::Config();
use DBI;
use vars qw(%c $dbh);
*c = \%EPP::Config::c;
$dbh = DBI->connect("DBI:mysql:$c{'mysql_database'}:$c{'mysql_host'}:$c{'mysql_port'}","$c{'mysql_username'}","$c{'mysql_password'}") or die "$DBI::errstr";


my $currency = 'USD';
my $from = 'registry@nic.xx';

my $sth0 = $dbh->prepare("SELECT `id`,`clid` FROM `registrar` ORDER BY `id`") or die $dbh->errst;
$sth0->execute() or die $sth0->errstr;
while (my $reg = $sth0->fetchrow_hashref()) {

	my $tmpl = HTML::Template->new(filename => '/var/www/cgi-bin/epp/cron/src/txt.tmpl');

	my $sth = $dbh->prepare("SELECT DATE_FORMAT(NOW()-INTERVAL 1 MONTH,'%Y-%m') AS `name`, DATE_FORMAT(NOW()-INTERVAL 1 MONTH,'%Y-%m-01') AS `from`, LAST_DAY(NOW()-INTERVAL 1 MONTH) AS `to`") or die $dbh->errst;
	$sth->execute() or die $sth->errstr;
	my $period = $sth->fetchrow_hashref();
	my $fileTag = $reg->{clid}.'_'.$period->{name};

	$sth = $dbh->prepare("SELECT `title`,`first_name`,`middle_name`,`last_name`,`org`,`street1`,`street2`,`street3`,`city`,`sp`,`pc`,`cc`,`email`
							FROM `registrar_contact`
							WHERE `registrar_id` = ? AND `type` = 'billing'
							LIMIT 1") or die $dbh->errst;
	$sth->execute($reg->{id}) or die $sth->errstr;
	my $contact = $sth->fetchrow_hashref();

	if (!$contact){warn("Registrar ID-".$reg->{id}." don't have Billing contact map");next;}
	$tmpl->param(
		'from_date' => $period->{from},
		'to_date' => $period->{to},
		'registrar_clid' => $reg->{clid},
		'contact_name' => "$contact->{first_name} $contact->{middle_name} $contact->{last_name}",
		'contact_org' => $contact->{org},
		'contact_street' => $contact->{street1},
		'contact_city' => $contact->{city},
		'contact_sp' => $contact->{sp},
		'contact_pc' => $contact->{pc},
		'contact_cc' => $contact->{cc}
	);

	my @rows;
	my $totalPrice = 0;
	$sth = $dbh->prepare("SELECT *,DATE_FORMAT(date,'%Y-%m-%d') AS `date` FROM `statement` WHERE `registrar_id`=? AND `date`>=? AND `date` <=? ORDER BY `date`") or die $dbh->errst;
	$sth->execute($reg->{id},$period->{from},$period->{to}) or die $sth->errstr;
	my $i=0;while (my $f = $sth->fetchrow_hashref()) {
		 $i++;
		$totalPrice += $f->{amount};
		push (@rows, { 'row' => sprintf("%6d %-10s %-15s %-32s %6d %-8s %6.2f %-8s", $i, $f->{date}, uc($f->{command}), uc($f->{domain_name}), $f->{length_in_months},"MONTHS", $f->{amount}, $currency )} );
	}
	$tmpl->param(
		'list' => \@rows,
		'total_price' => sprintf("%.2f",$totalPrice),
		'currency' => $currency
	);
	#=============================================================================================================================================
	@rows = ();
	$totalPrice = 0;
	my $pdfTmpl = HTML::Template->new(filename => "/var/www/cgi-bin/epp/cron/src/pdf.tmpl");
	$pdfTmpl->param(
		'from_date' => $period->{from},
		'to_date' => $period->{to},
		'registrar_clid' => $reg->{clid},
		'contact_name' => "$contact->{first_name} $contact->{middle_name} $contact->{last_name}",
		'contact_org' => $contact->{org},
		'contact_street' => $contact->{street1},
		'contact_city' => $contact->{city},
		'contact_sp' => $contact->{sp},
		'contact_pc' => $contact->{pc},
		'contact_cc' => $contact->{cc}
	);
	$sth = $dbh->prepare("SELECT DISTINCT `command`,`length_in_months`,SUM(`amount`) AS `sum`,COUNT(*) AS `count` FROM `statement` WHERE `registrar_id`=? AND `date`>=? AND `date`<=? GROUP BY `command`,`length_in_months` ORDER BY `command`,`length_in_months`") or die $dbh->errst;
	$sth->execute($reg->{id},$period->{from},$period->{to}) or die $sth->errstr;
	$i=0;
	while (my $f = $sth->fetchrow_hashref()) {
		$i++;
		$totalPrice += $f->{sum};
		push (@rows, {
			'nr' => $i,
			'item' => uc($f->{command})." - $f->{length_in_months} MONTH".( $f->{length_in_months}==1 ? '' : 'S' ),
			'count' => $f->{count},
			'sum' => $f->{sum}
		});
	}
	$pdfTmpl->param(
		'list' => \@rows,
		'total_price' => sprintf("%.2f",$totalPrice),
		'currency' => $currency
	);
	open(FILE, '>', "/var/www/cgi-bin/epp/cron/invoice/${fileTag}.pdf-html");
	print FILE $pdfTmpl->output();
	close FILE;
	system("htmldoc -v -t pdf --book --webpage --no-title --no-numbered --pagemode document --footer right --size a4 --top 0mm --left 14mm --right 14mm --bottom 0mm --textfont helvetica --bodyfont helvetica --fontsize 10 -f /var/www/cgi-bin/epp/cron/invoice/${fileTag}.pdf /var/www/cgi-bin/epp/cron/invoice/${fileTag}.pdf-html ");
	unlink("/var/www/cgi-bin/epp/cron/invoice/${fileTag}.pdf-html");
#	print $pdfTmpl->output();exit;
	#=============================================================================================================================================
	my $mTmpl = HTML::Template->new(filename => '/var/www/cgi-bin/epp/cron/src/mail.tmpl');
	$mTmpl->param(
		'registrar_clid' => $reg->{clid},
		'total_price' => sprintf("%.2f",$totalPrice),
		'currency' => $currency
	);
	my $mail = MIME::Lite->new(
		'From' => $from,
		'To' => $contact->{email},
		'Subject' => "Invoice $period->{from} - $period->{to}",
		'Type' => 'multipart/mixed'
	);
	$mail->attr('content-type.charset' => 'UTF-8');
	$mail->attach(
		'Type' => 'text/plain',
		'Data' => $mTmpl->output()
	);
	$mail->attach(
		'Type' => 'text/plain',
		'Filename' => $fileTag.'.txt',
		'Data' => $tmpl->output()
	);
	$mail->attach(
		'Type' => 'application/pdf',
		'Filename' => $fileTag.'.pdf',
		'Path' => "/var/www/cgi-bin/epp/cron/invoice/${fileTag}.pdf"
	);
	$mail->send();
}