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
#	(c) Copyright 2014 XPanel Ltd.
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



#
# This is a specific error script for schema errors.
# It is called if mod_epp cannot find required tags.
#
use CGI qw/:standard/;
use POSIX 'strftime';

$q = new CGI;


my $cltrid = $q->param('clTRID');
my $code = $q->param('code');
my $msg = $q->param('msg');
my $s = strftime("%Y%m%d%H%M%S", localtime);

$cltrid = 'non-specified' unless (defined($cltrid));
$code = 2400 unless (defined($code));
$msg = 'generic error' unless (defined($msg));

my $debug = 0;

my $close = '';

$close  = "Connection: close\r\n" if ($code =~ /^\d5\d\d$/);

print "Content-Type: text/plain\r\n$close\r\n";

print <<EOM;
<?xml version="1.0" encoding="UTF-8" standalone="no"?>

<!-- EPP schema ERROR: mod_epp could not parse your request. -->

<epp xmlns="urn:ietf:params:xml:ns:epp-1.0"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="urn:ietf:params:xml:ns:epp-1.0
     epp-1.0.xsd">
  <response>
    <result code="$code">
      <msg>$msg</msg>
    </result>
    <trID>
      <clTRID>$cltrid</clTRID>
      <svTRID>$s</svTRID>
    </trID>
  </response>
</epp>
EOM