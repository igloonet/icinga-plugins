#!/usr/bin/ruby

# Copyright (c) 2010 IglooNET, s.r.o.   http://www.igloonet.cz/
#         
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#           
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#   
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

require 'singleton'
require 'optparse'

OK=0
WARN=1
CRIT=2

class ChefClientCheckPlugin
  include Singleton
  ID = 'ChefClientCheckPlugin 0.1'
  attr_accessor :settings
  
  def initialize
    # default settings
    self.settings = {
      :chef_failed_file => '/var/run/chef_run_failed',
      :failed_returns => CRIT
    }

    begin
      get_options
    rescue ArgumentError => e
      puts e.message; exit(3)
    end
  end
  
  def get_options
    OptionParser.new do |opts|
      opts.banner = "Usage: #{File.basename $0} [options]"
      opts.separator ""
      opts.separator "Specific options:"
      
      opts.on('-f', '--file', 'Location of chef_run_failed file including filename') do |file|
        self.settings[:chef_failed_file] = file
      end
      opts.on('-w', '--failed-warning', 'If chef client failed, return warning not critical') {
        self.settings[:failed_returns] = WARN
      }
      opts.on('-h', '--help', 'Show this message and exit') { puts opts; exit}
      opts.on('-v', '--version', 'Print version info and exit') { puts ID; exit }
      
    end.parse!
  end

  def check
    result = File.exists?(self.settings[:chef_failed_file]) ? self.settings[:failed_returns] : OK
    puts "Chef client check #{status(result)}"
    exit(result)
  end
  
  def status(result)
    case result
    when OK: 'OK'
    when WARN: 'WARNING'
    when CRIT: 'CRITICAL'
    end
  end
end

ChefClientCheckPlugin.instance.check

